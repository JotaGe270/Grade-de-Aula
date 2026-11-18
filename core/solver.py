import math
import random
import time as pytime
from collections import defaultdict


class HybridTimetableSolver:
    """
    Motor Híbrido de Otimização de Grade Acadêmica:
    Combina Simulated Annealing (SA) + Tabu Search (TS) para alocar aulas
    respeitando as disponibilidades dos professores (Availability),
    limites de carga horária, conflitos de curso/professor, e priorizando
    aulas seguidas (geminadas) da mesma matéria no mesmo dia.
    """

    HARD_UNASSIGNED = 10_000
    HARD_COURSE_CONFLICT = 2_500
    HARD_PROF_CONFLICT = 2_500
    HARD_OVERLOAD = 2_000

    SOFT_UNQUALIFIED_PROF = 80
    SOFT_SPLIT_PROFESSOR = 40
    SOFT_SPLIT_SUBJECT_DAYS = 35
    SOFT_NON_CONSECUTIVE = 25
    SOFT_NON_PREFERRED_DAY = 15
    SOFT_PROF_GAP = 8
    SOFT_LOAD_BALANCE = 10

    def __init__(self, slots, subjects, professors, mode="hybrid", seed=None,
                 max_sa_iterations=600, max_ts_iterations=250, tabu_tenure=9):
        """
        slots: list of dicts {id, weekday, start, end, duration_mins}
        subjects: list of dicts {id, name, code, course_id, course_name, weekly_lessons, preferred_days, qualified_prof_ids}
        professors: list of dicts {id, full_name, max_weekly_mins, available_slot_ids}
        mode: 'hybrid' | 'sa' | 'tabu'
        """
        self.rng = random.Random(seed)
        self.mode = mode if mode in ("hybrid", "sa", "tabu") else "hybrid"
        self.max_sa_iterations = max_sa_iterations
        self.max_ts_iterations = max_ts_iterations
        self.tabu_tenure = tabu_tenure

        self.slots = {s["id"]: s for s in slots}
        self.slot_list = list(slots)
        self.subjects = {s["id"]: s for s in subjects}
        self.subject_list = list(subjects)
        self.professors = {p["id"]: p for p in professors}
        self.prof_list = list(professors)

        # Precompute ordering of slots per weekday for consecutive/gap calculation
        self.slots_by_day = defaultdict(list)
        for s in sorted(self.slot_list, key=lambda x: (x["weekday"], x["start"])):
            self.slots_by_day[s["weekday"]].append(s["id"])
        self.slot_day_index = {}
        for day, sids in self.slots_by_day.items():
            for idx, sid in enumerate(sids):
                self.slot_day_index[sid] = (day, idx)
        self.max_slots_in_a_day = max((len(v) for v in self.slots_by_day.values()), default=4)

        # Build lesson demands: one entry per weekly lesson of each subject
        self.demands = []
        self.demands_by_subject = defaultdict(list)
        # Map subject_id -> list of valid (prof_id, slot_id) pairs based on Availability
        self.valid_pairs_by_subject = {}

        for s in self.subject_list:
            sid = s["id"]
            qual_ids = set(s.get("qualified_prof_ids") or [])
            pairs = []
            for p in self.prof_list:
                pid = p["id"]
                if qual_ids and pid not in qual_ids:
                    continue
                for slot_id in p["available_slot_ids"]:
                    if slot_id in self.slots:
                        pairs.append((pid, slot_id))
            pairs.sort(key=lambda ps: (ps[0], ps[1]))
            self.valid_pairs_by_subject[sid] = pairs

        # Order subjects by difficulty (most constrained first: fewer valid pairs, more weekly lessons)
        ordered_subjects = sorted(
            self.subject_list,
            key=lambda s: (len(self.valid_pairs_by_subject[s["id"]]), -s["weekly_lessons"], s["id"]),
        )
        for s in ordered_subjects:
            for i in range(s["weekly_lessons"]):
                d_idx = len(self.demands)
                self.demands.append({
                    "index": d_idx,
                    "subject_id": s["id"],
                    "lesson_num": i,
                })
                self.demands_by_subject[s["id"]].append(d_idx)

    def _is_qualified(self, subject_id, prof_id):
        qual = self.subjects[subject_id].get("qualified_prof_ids")
        if not qual:
            return True
        return prof_id in qual

    def evaluate_detailed(self, state):
        """
        Calcula o custo total de um estado `state` (lista onde state[i] = (prof_id, slot_id) ou None).
        Prioriza que aulas da mesma matéria fiquem no mesmo dia e em horários seguidos (geminadas).
        """
        unassigned = 0
        course_conflicts = 0
        prof_conflicts = 0
        overload_violations = 0

        unqualified_count = 0
        split_prof_count = 0
        split_subject_days = 0
        non_consecutive_lessons = 0
        non_preferred_days = 0
        prof_gaps = 0
        load_balance_cost = 0.0

        course_slot_used = defaultdict(int)
        prof_slot_used = defaultdict(int)
        prof_mins = defaultdict(int)
        subj_profs = defaultdict(set)
        subj_day_indices = defaultdict(lambda: defaultdict(list))
        prof_day_indices = defaultdict(lambda: defaultdict(list))

        for d_idx, assignment in enumerate(state):
            if assignment is None:
                unassigned += 1
                continue
            prof_id, slot_id = assignment
            subj_id = self.demands[d_idx]["subject_id"]
            subj = self.subjects[subj_id]
            slot = self.slots[slot_id]
            course_id = subj["course_id"]
            weekday = slot["weekday"]

            # Track usage for conflict detection
            course_slot_used[(course_id, slot_id)] += 1
            prof_slot_used[(prof_id, slot_id)] += 1
            prof_mins[prof_id] += slot["duration_mins"]

            # Soft tracking
            if not self._is_qualified(subj_id, prof_id):
                unqualified_count += 1
            subj_profs[subj_id].add(prof_id)

            pref_days = subj.get("preferred_days") or []
            if pref_days and weekday not in pref_days:
                non_preferred_days += 1

            _, day_pos = self.slot_day_index[slot_id]
            subj_day_indices[subj_id][weekday].append(day_pos)
            prof_day_indices[prof_id][weekday].append(day_pos)

        for count in course_slot_used.values():
            if count > 1:
                course_conflicts += (count - 1)

        for count in prof_slot_used.values():
            if count > 1:
                prof_conflicts += (count - 1)

        for prof_id, mins in prof_mins.items():
            max_mins = self.professors[prof_id]["max_weekly_mins"]
            if mins > max_mins:
                excess = mins - max_mins
                overload_violations += 1 + math.ceil(excess / 50.0)
            if max_mins > 0:
                ratio = min(2.0, mins / max_mins)
                load_balance_cost += (ratio ** 2) * self.SOFT_LOAD_BALANCE

        for subj_id, pset in subj_profs.items():
            if len(pset) > 1:
                split_prof_count += (len(pset) - 1)

        # Penalize splitting a subject across different days or non-consecutive slots on the same day
        for subj_id, days_map in subj_day_indices.items():
            total_alloc_for_subj = sum(len(pos_list) for pos_list in days_map.values())
            if total_alloc_for_subj > 1:
                min_days_needed = max(1, math.ceil(total_alloc_for_subj / max(1, self.max_slots_in_a_day)))
                if len(days_map) > min_days_needed:
                    split_subject_days += (len(days_map) - min_days_needed)

                for pos_list in days_map.values():
                    if len(pos_list) > 1:
                        pos_list.sort()
                        span = pos_list[-1] - pos_list[0] + 1
                        gaps = span - len(pos_list)
                        if gaps > 0:
                            non_consecutive_lessons += gaps

        for prof_id, days_map in prof_day_indices.items():
            for indices in days_map.values():
                if len(indices) > 1:
                    indices.sort()
                    span = indices[-1] - indices[0] + 1
                    gaps = span - len(indices)
                    if gaps > 0:
                        prof_gaps += gaps

        hard_cost = (
            unassigned * self.HARD_UNASSIGNED
            + course_conflicts * self.HARD_COURSE_CONFLICT
            + prof_conflicts * self.HARD_PROF_CONFLICT
            + overload_violations * self.HARD_OVERLOAD
        )
        soft_cost = (
            unqualified_count * self.SOFT_UNQUALIFIED_PROF
            + split_prof_count * self.SOFT_SPLIT_PROFESSOR
            + split_subject_days * self.SOFT_SPLIT_SUBJECT_DAYS
            + non_consecutive_lessons * self.SOFT_NON_CONSECUTIVE
            + non_preferred_days * self.SOFT_NON_PREFERRED_DAY
            + prof_gaps * self.SOFT_PROF_GAP
            + round(load_balance_cost, 2)
        )

        return {
            "total_cost": round(hard_cost + soft_cost, 2),
            "hard_cost": hard_cost,
            "soft_cost": round(soft_cost, 2),
            "unassigned": unassigned,
            "course_conflicts": course_conflicts,
            "prof_conflicts": prof_conflicts,
            "overload_violations": overload_violations,
            "unqualified_count": unqualified_count,
            "split_subject_days": split_subject_days,
            "non_consecutive_lessons": non_consecutive_lessons,
            "same_day_repeats": split_subject_days,
            "non_preferred_days": non_preferred_days,
            "prof_gaps": prof_gaps,
        }

    def cost(self, state):
        return self.evaluate_detailed(state)["total_cost"]

    def build_initial_solution(self):
        """
        Fase 0: Heurística construtiva gulosa orientada por restrições.
        Prioriza alocar aulas da mesma disciplina seguidas (geminadas) no mesmo dia e com o mesmo professor.
        """
        state = [None] * len(self.demands)
        used_course_slot = set()
        used_prof_slot = set()
        prof_mins = defaultdict(int)
        subj_positions = defaultdict(list)  # sid -> list of (weekday, day_pos)
        subj_prof = {}

        for d_idx, demand in enumerate(self.demands):
            sid = demand["subject_id"]
            subj = self.subjects[sid]
            course_id = subj["course_id"]
            pref_days = set(subj.get("preferred_days") or [])
            candidates = self.valid_pairs_by_subject[sid]
            candidate_set = set(candidates)

            best_pair = None
            best_score = float("inf")

            for pid, slot_id in candidates:
                slot = self.slots[slot_id]
                dur = slot["duration_mins"]
                max_mins = self.professors[pid]["max_weekly_mins"]

                # Check hard constraints first
                if (course_id, slot_id) in used_course_slot:
                    continue
                if (pid, slot_id) in used_prof_slot:
                    continue
                if prof_mins[pid] + dur > max_mins:
                    continue

                weekday, day_pos = self.slot_day_index[slot_id]

                # Compute soft score
                score = 0.0
                if not self._is_qualified(sid, pid):
                    score += self.SOFT_UNQUALIFIED_PROF
                if sid in subj_prof and subj_prof[sid] != pid:
                    score += self.SOFT_SPLIT_PROFESSOR

                existing_pos = subj_positions[sid]
                if existing_pos:
                    # Prefer same day and immediately consecutive slot!
                    same_day_pos = [pos for (d, pos) in existing_pos if d == weekday]
                    if same_day_pos:
                        min_dist = min(abs(day_pos - pos) for pos in same_day_pos)
                        if min_dist == 1:
                            score -= 20.0  # Strong bonus for back-to-back lessons on same day
                        else:
                            score += self.SOFT_NON_CONSECUTIVE * (min_dist - 1)
                    else:
                        score += self.SOFT_SPLIT_SUBJECT_DAYS
                elif subj["weekly_lessons"] >= 2:
                    # First lesson of a multi-lesson subject: check if an adjacent slot on the same day is also free & available
                    day_slots = self.slots_by_day[weekday]
                    has_adjacent_free = False
                    for adj_idx in (day_pos - 1, day_pos + 1):
                        if 0 <= adj_idx < len(day_slots):
                            adj_slot_id = day_slots[adj_idx]
                            if (
                                (pid, adj_slot_id) in candidate_set
                                and (course_id, adj_slot_id) not in used_course_slot
                                and (pid, adj_slot_id) not in used_prof_slot
                                and prof_mins[pid] + dur + self.slots[adj_slot_id]["duration_mins"] <= max_mins
                            ):
                                has_adjacent_free = True
                                break
                    if has_adjacent_free:
                        score -= 15.0

                if pref_days and weekday not in pref_days:
                    score += self.SOFT_NON_PREFERRED_DAY
                score += (prof_mins[pid] / max(1, max_mins)) * self.SOFT_LOAD_BALANCE

                if score < best_score:
                    best_score = score
                    best_pair = (pid, slot_id)

            if best_pair is not None:
                pid, slot_id = best_pair
                state[d_idx] = best_pair
                used_course_slot.add((course_id, slot_id))
                used_prof_slot.add((pid, slot_id))
                prof_mins[pid] += self.slots[slot_id]["duration_mins"]
                subj_positions[sid].append(self.slot_day_index[slot_id])
                subj_prof.setdefault(sid, pid)

        return state

    def _find_suboptimal_demands(self, state):
        """Identifica índices de aulas não alocadas, não geminadas ou fora do dia preferido."""
        flagged = []
        for i, v in enumerate(state):
            if v is None:
                flagged.append(i)
            else:
                sid = self.demands[i]["subject_id"]
                pref = self.subjects[sid].get("preferred_days") or []
                if pref and self.slots[v[1]]["weekday"] not in pref:
                    flagged.append(i)

        for sid, d_indices in self.demands_by_subject.items():
            if len(d_indices) < 2:
                continue
            assigned = [(d, self.slot_day_index[state[d][1]]) for d in d_indices if state[d] is not None]
            if len(assigned) < 2:
                continue
            days = {pos[0] for _, pos in assigned}
            if len(days) > 1:
                flagged.extend(d_indices)
            else:
                positions = sorted(pos[1] for _, pos in assigned)
                if positions[-1] - positions[0] + 1 > len(positions):
                    flagged.extend(d_indices)
        return list(set(flagged))

    def _generate_neighbors(self, state, count=20):
        """
        Gera vizinhos aplicando operadores de:
        1. Agrupamento Consecutivo (move aula irmã para slot adjacente no mesmo dia)
        2. Reatribuição com Cadeia de Deslocamento (Ejection Chain)
        3. Permutação de horários entre duas aulas (Swap)
        """
        neighbors = []
        n_demands = len(self.demands)
        if n_demands == 0:
            return neighbors

        problem_indices = self._find_suboptimal_demands(state)

        for _ in range(count):
            if problem_indices and self.rng.random() < 0.65:
                d1 = self.rng.choice(problem_indices)
            else:
                d1 = self.rng.randrange(n_demands)

            sid1 = self.demands[d1]["subject_id"]
            subj1 = self.subjects[sid1]
            c1 = subj1["course_id"]
            pairs1 = self.valid_pairs_by_subject[sid1]
            if not pairs1:
                continue

            op_roll = self.rng.random()

            # Operator 1: Direct reassignment or Consecutive Pairing + Ejection Chain
            if op_roll < 0.65 or n_demands < 2:
                old_pair = state[d1]
                sibling_indices = [idx for idx in self.demands_by_subject[sid1] if idx != d1 and state[idx] is not None]

                # Try pairing consecutively next to a sibling lesson of the same subject 50% of the time
                new_pair = None
                if sibling_indices and self.rng.random() < 0.55:
                    sib_idx = self.rng.choice(sibling_indices)
                    sib_pid, sib_slot = state[sib_idx]
                    sib_day, sib_pos = self.slot_day_index[sib_slot]
                    day_slots = self.slots_by_day[sib_day]
                    adj_candidates = []
                    for adj_pos in (sib_pos - 1, sib_pos + 1):
                        if 0 <= adj_pos < len(day_slots):
                            adj_slot = day_slots[adj_pos]
                            if (sib_pid, adj_slot) in pairs1:
                                adj_candidates.append((sib_pid, adj_slot))
                            else:
                                adj_candidates.extend((p, sl) for (p, sl) in pairs1 if sl == adj_slot)
                    if adj_candidates:
                        new_pair = self.rng.choice(adj_candidates)

                if new_pair is None:
                    new_pair = self.rng.choice(pairs1)

                if new_pair == old_pair:
                    continue

                target_pid, target_slot = new_pair
                new_state = list(state)
                new_state[d1] = new_pair

                # Relocate any lesson d2 that now collides on course+slot or prof+slot
                for d2, asg2 in enumerate(state):
                    if d2 == d1 or asg2 is None:
                        continue
                    p2, s2 = asg2
                    sid2 = self.demands[d2]["subject_id"]
                    c2 = self.subjects[sid2]["course_id"]
                    if s2 == target_slot and (c2 == c1 or p2 == target_pid):
                        pairs2 = self.valid_pairs_by_subject[sid2]
                        if pairs2:
                            occupied_course = {
                                (self.subjects[self.demands[k]["subject_id"]]["course_id"], new_state[k][1])
                                for k in range(n_demands) if k != d2 and new_state[k] is not None
                            }
                            occupied_prof = {
                                (new_state[k][0], new_state[k][1])
                                for k in range(n_demands) if k != d2 and new_state[k] is not None
                            }
                            prof_load = defaultdict(int)
                            for k in range(n_demands):
                                if k != d2 and new_state[k] is not None:
                                    prof_load[new_state[k][0]] += self.slots[new_state[k][1]]["duration_mins"]

                            sample2 = self.rng.sample(pairs2, min(len(pairs2), 16))
                            relocated = False
                            for cand_p2, cand_s2 in sample2:
                                dur2 = self.slots[cand_s2]["duration_mins"]
                                if (
                                    (c2, cand_s2) not in occupied_course
                                    and (cand_p2, cand_s2) not in occupied_prof
                                    and prof_load[cand_p2] + dur2 <= self.professors[cand_p2]["max_weekly_mins"]
                                ):
                                    new_state[d2] = (cand_p2, cand_s2)
                                    relocated = True
                                    break
                            if not relocated and old_pair is not None:
                                old_p1, old_s1 = old_pair
                                cand2_at_old = [p for (p, sl) in pairs2 if sl == old_s1]
                                if cand2_at_old:
                                    new_state[d2] = (cand2_at_old[0], old_s1)

                move_key = ("assign", d1, new_pair)
                rev_key = ("assign", d1, old_pair)
                neighbors.append((new_state, move_key, rev_key))

            # Operator 2: Swap slots between two demands or entire subject blocks
            else:
                d2 = self.rng.randrange(n_demands)
                if d1 == d2:
                    continue
                asg1, asg2 = state[d1], state[d2]
                if asg1 is None or asg2 is None:
                    continue
                sid2 = self.demands[d2]["subject_id"]
                pairs2 = self.valid_pairs_by_subject[sid2]
                if not pairs2:
                    continue

                # Try full Subject Block Swap when both subjects have the same number of allocated lessons
                d_list1 = [idx for idx in self.demands_by_subject[sid1] if state[idx] is not None]
                d_list2 = [idx for idx in self.demands_by_subject[sid2] if state[idx] is not None]
                if sid1 != sid2 and len(d_list1) == len(d_list2) and len(d_list1) >= 2 and self.rng.random() < 0.65:
                    new_state = list(state)
                    valid_block = True
                    for idx1, idx2 in zip(d_list1, d_list2):
                        p1_cur, s1_cur = state[idx1]
                        p2_cur, s2_cur = state[idx2]
                        cand1 = [p for (p, sl) in pairs1 if sl == s2_cur]
                        cand2 = [p for (p, sl) in pairs2 if sl == s1_cur]
                        if not cand1 or not cand2:
                            valid_block = False
                            break
                        np1 = p1_cur if p1_cur in cand1 else cand1[0]
                        np2 = p2_cur if p2_cur in cand2 else cand2[0]
                        new_state[idx1] = (np1, s2_cur)
                        new_state[idx2] = (np2, s1_cur)
                    if valid_block:
                        move_key = ("block_swap", min(sid1, sid2), max(sid1, sid2))
                        neighbors.append((new_state, move_key, move_key))
                        continue

                p1, s1 = asg1
                p2, s2 = asg2
                if s1 == s2:
                    continue
                cand1 = [p for (p, sl) in pairs1 if sl == s2]
                cand2 = [p for (p, sl) in pairs2 if sl == s1]
                if not cand1 or not cand2:
                    continue
                np1 = p1 if p1 in cand1 else self.rng.choice(cand1)
                np2 = p2 if p2 in cand2 else self.rng.choice(cand2)
                new_state = list(state)
                new_state[d1] = (np1, s2)
                new_state[d2] = (np2, s1)
                move_key = ("swap", min(d1, d2), max(d1, d2), s2, s1)
                rev_key = ("swap", min(d1, d2), max(d1, d2), s1, s2)
                neighbors.append((new_state, move_key, rev_key))

        return neighbors

    def run_simulated_annealing(self, initial_state, use_tabu_memory=True):
        """
        Fase 1: Simulated Annealing (com Memória Tabu integrada quando no modo híbrido).
        """
        current = list(initial_state)
        current_cost = self.cost(current)
        best = list(current)
        best_cost = current_cost

        T_init = 120.0
        T = T_init
        T_min = 0.25
        alpha = 0.985

        tabu_memory = {}
        short_tenure = max(4, self.tabu_tenure // 2)
        improvements = 0
        stagnation = 0

        for it in range(1, self.max_sa_iterations + 1):
            if best_cost == 0:
                break

            candidates = self._generate_neighbors(current, count=4)
            if not candidates:
                break

            chosen = None
            chosen_cost = float("inf")
            for cand_state, move_key, rev_key in candidates:
                c_cost = self.cost(cand_state)
                is_tabu = use_tabu_memory and tabu_memory.get(move_key, 0) > it
                if is_tabu and c_cost >= best_cost:
                    continue
                if c_cost < chosen_cost:
                    chosen = (cand_state, move_key, rev_key, c_cost)
                    chosen_cost = c_cost

            if chosen is None:
                cand_state, move_key, rev_key = candidates[0]
                chosen = (cand_state, move_key, rev_key, self.cost(cand_state))

            cand_state, move_key, rev_key, cand_cost = chosen
            delta = cand_cost - current_cost

            accept = False
            if delta <= 0:
                accept = True
            else:
                prob = math.exp(-delta / max(T, 1e-6))
                if self.rng.random() < prob:
                    accept = True

            if accept:
                current = cand_state
                current_cost = cand_cost
                if use_tabu_memory:
                    tabu_memory[rev_key] = it + short_tenure

                if current_cost < best_cost:
                    best = list(current)
                    best_cost = current_cost
                    improvements += 1
                    stagnation = 0
                else:
                    stagnation += 1
            else:
                stagnation += 1

            if stagnation >= 80:
                T = max(T, T_init * 0.35)
                current = list(best)
                current_cost = best_cost
                stagnation = 0
            else:
                T = max(T_min, T * alpha)

        return best, best_cost, improvements

    def run_tabu_search(self, initial_state):
        """
        Fase 2: Tabu Search de Intensificação.
        """
        current = list(initial_state)
        current_cost = self.cost(current)
        best = list(current)
        best_cost = current_cost

        tabu_list = {}
        improvements = 0
        no_improve_iters = 0

        for it in range(1, self.max_ts_iterations + 1):
            if best_cost == 0:
                break

            neighbors = self._generate_neighbors(current, count=18)
            if not neighbors:
                break

            best_candidate = None
            best_cand_cost = float("inf")
            best_rev_key = None

            for cand_state, move_key, rev_key in neighbors:
                cand_cost = self.cost(cand_state)
                is_tabu = tabu_list.get(move_key, 0) > it

                if is_tabu and cand_cost >= best_cost:
                    continue

                if cand_cost < best_cand_cost:
                    best_cand_cost = cand_cost
                    best_candidate = cand_state
                    best_rev_key = rev_key

            if best_candidate is None:
                cand_state, _, rev_key = neighbors[0]
                best_candidate = cand_state
                best_cand_cost = self.cost(cand_state)
                best_rev_key = rev_key

            current = best_candidate
            current_cost = best_cand_cost
            if best_rev_key is not None:
                tenure = self.tabu_tenure + self.rng.randint(-2, 2)
                tabu_list[best_rev_key] = it + max(3, tenure)

            if current_cost < best_cost:
                best = list(current)
                best_cost = current_cost
                improvements += 1
                no_improve_iters = 0
            else:
                no_improve_iters += 1

            if no_improve_iters >= 90:
                break

        return best, best_cost, improvements

    def _sanitize_and_build_result(self, best_state, metrics):
        used_course_slot = set()
        used_prof_slot = set()
        prof_mins = defaultdict(int)
        clean_state = [None] * len(best_state)

        for d_idx, asg in enumerate(best_state):
            if asg is None:
                continue
            pid, slot_id = asg
            sid = self.demands[d_idx]["subject_id"]
            course_id = self.subjects[sid]["course_id"]
            dur = self.slots[slot_id]["duration_mins"]
            max_mins = self.professors[pid]["max_weekly_mins"]

            if slot_id not in self.professors[pid]["available_slot_ids"]:
                continue
            if (course_id, slot_id) in used_course_slot:
                continue
            if (pid, slot_id) in used_prof_slot:
                continue
            if prof_mins[pid] + dur > max_mins:
                continue

            clean_state[d_idx] = (pid, slot_id)
            used_course_slot.add((course_id, slot_id))
            used_prof_slot.add((pid, slot_id))
            prof_mins[pid] += dur

        for d_idx, asg in enumerate(clean_state):
            if asg is not None:
                continue
            sid = self.demands[d_idx]["subject_id"]
            course_id = self.subjects[sid]["course_id"]
            for pid, slot_id in self.valid_pairs_by_subject[sid]:
                dur = self.slots[slot_id]["duration_mins"]
                max_mins = self.professors[pid]["max_weekly_mins"]
                if (course_id, slot_id) not in used_course_slot and (pid, slot_id) not in used_prof_slot and prof_mins[pid] + dur <= max_mins:
                    clean_state[d_idx] = (pid, slot_id)
                    used_course_slot.add((course_id, slot_id))
                    used_prof_slot.add((pid, slot_id))
                    prof_mins[pid] += dur
                    break

        alloc = []
        done_by_subject = defaultdict(int)

        for d_idx, asg in enumerate(clean_state):
            if asg is None:
                continue
            pid, slot_id = asg
            sid = self.demands[d_idx]["subject_id"]
            subj = self.subjects[sid]
            prof = self.professors[pid]
            slot = self.slots[slot_id]
            done_by_subject[sid] += 1
            alloc.append({
                "subjectId": sid,
                "subject": subj["name"],
                "code": subj["code"],
                "courseId": subj["course_id"],
                "course": subj["course_name"],
                "professor": prof["full_name"],
                "professorId": pid,
                "slotId": slot_id,
                "weekday": slot["weekday"],
                "start": slot["start"],
                "end": slot["end"],
            })

        alloc.sort(key=lambda a: (a["weekday"], a["start"], a["course"], a["subject"]))

        pending = []
        for subj in self.subject_list:
            sid = subj["id"]
            done = done_by_subject[sid]
            missing = subj["weekly_lessons"] - done
            if missing > 0:
                diag = self._diagnose_missing(subj, missing, alloc, used_course_slot, used_prof_slot, prof_mins)
                pending.append({
                    "subjectId": sid,
                    "subject": subj["name"],
                    "course": subj["course_name"],
                    "professor": diag["professor"],
                    "missing": missing,
                    "reason": diag["reason"],
                    "suggestion": diag["suggestion"],
                })

        final_eval = self.evaluate_detailed(clean_state)
        total_lessons = sum(s["weekly_lessons"] for s in self.subject_list)

        return {
            "alloc": alloc,
            "pending": pending,
            "total": total_lessons,
            "metrics": {
                **metrics,
                "final_cost": final_eval["total_cost"],
                "hard_conflicts": (
                    final_eval["course_conflicts"]
                    + final_eval["prof_conflicts"]
                    + final_eval["overload_violations"]
                ),
                "soft_cost": final_eval["soft_cost"],
                "split_subject_days": final_eval["split_subject_days"],
                "non_consecutive_lessons": final_eval["non_consecutive_lessons"],
                "same_day_repeats": final_eval["same_day_repeats"],
                "non_preferred_days": final_eval["non_preferred_days"],
                "prof_gaps": final_eval["prof_gaps"],
            },
        }

    def _format_free_slot_windows(self, course_id, used_course_slot, needed_count, filter_slot_ids=None):
        days_names = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"]
        free_by_day = defaultdict(list)
        for sl in sorted(self.slot_list, key=lambda x: (x["weekday"], x["start"])):
            if (course_id, sl["id"]) not in used_course_slot:
                if filter_slot_ids is None or sl["id"] in filter_slot_ids:
                    free_by_day[sl["weekday"]].append(sl)

        windows = []
        # Prioritize days that can host `needed_count` consecutive/same-day lessons
        sorted_days = sorted(
            free_by_day.items(),
            key=lambda kv: (0 if len(kv[1]) >= needed_count else 1, kv[0]),
        )
        for day_idx, s_list in sorted_days[:2]:
            picked = s_list[:max(1, needed_count)]
            times_str = ", ".join(f"{s['start'][:5]}–{s['end'][:5]}" for s in picked)
            windows.append(f"{days_names[day_idx]} ({times_str})")

        return " ou ".join(windows) if windows else "nenhum horário livre restante na grade do curso"

    def _diagnose_missing(self, subj, missing, alloc, used_course_slot, used_prof_slot, prof_mins):
        qual_ids = subj.get("qualified_prof_ids") or []
        if qual_ids:
            target_profs = [self.professors[pid] for pid in qual_ids if pid in self.professors]
        else:
            target_profs = list(self.prof_list)

        prof_names = ", ".join(p["full_name"] for p in target_profs) if target_profs else "Sem professor atribuído"
        course_id = subj["course_id"]
        free_windows = self._format_free_slot_windows(course_id, used_course_slot, missing)

        if not self.prof_list:
            return {
                "professor": "Nenhum",
                "reason": "Nenhum professor ativo cadastrado.",
                "suggestion": "Solicitar ao Gestor o cadastro de professores ativos.",
            }

        sid = subj["id"]
        pairs = self.valid_pairs_by_subject[sid]
        if not pairs:
            return {
                "professor": prof_names,
                "reason": "Nenhum horário disponível marcado pelo(s) docente(s) habilitado(s).",
                "suggestion": (
                    f"Falar com {prof_names} para marcar disponibilidade no sistema "
                    f"(sugestão de horários livres na turma: {free_windows})."
                ),
            }

        reasons = set()
        has_overload = False
        has_slot_clash = False
        prof_marked_slots = {slot_id for _, slot_id in pairs}

        for pid, slot_id in pairs:
            dur = self.slots[slot_id]["duration_mins"]
            max_mins = self.professors[pid]["max_weekly_mins"]
            if (course_id, slot_id) in used_course_slot:
                reasons.add("Horários disponíveis já ocupados por outras disciplinas do curso.")
                has_slot_clash = True
            if (pid, slot_id) in used_prof_slot:
                reasons.add("Professor já está alocado em outra aula nesses mesmos horários.")
                has_slot_clash = True
            if prof_mins[pid] + dur > max_mins:
                reasons.add("Carga horária semanal máxima do professor foi atingida.")
                has_overload = True

        # Check if professor already has free slots marked that only failed due to max_weekly_hours overload
        free_prof_slots = {
            slot_id for (pid, slot_id) in pairs
            if (course_id, slot_id) not in used_course_slot and (pid, slot_id) not in used_prof_slot
        }

        suggestions = []
        if has_overload and free_prof_slots:
            avail_free_windows = self._format_free_slot_windows(
                course_id, used_course_slot, missing, filter_slot_ids=free_prof_slots
            )
            needed_hours = math.ceil((missing * subj.get("lesson_minutes", 50)) / 60.0)
            suggestions.append(
                f"Falar com o Gestor para ampliar a carga semanal máxima de {prof_names} em +{needed_hours}h "
                f"(docente já tem disponibilidade livre em {avail_free_windows}), "
                f"ou atribuir outro professor para dividir a disciplina."
            )
        elif has_slot_clash:
            # Identify who is occupying the slots that this professor marked
            blocking = [
                a for a in alloc
                if a["slotId"] in prof_marked_slots
                and (a["courseId"] == course_id or a["professorId"] in {p["id"] for p in target_profs})
            ]
            own_clash_subjs = sorted({a["subject"] for a in blocking if a["professorId"] in {p["id"] for p in target_profs}})
            other_clash = [a for a in blocking if a["professorId"] not in {p["id"] for p in target_profs}]

            if own_clash_subjs:
                subjs_txt = ", ".join(own_clash_subjs)
                suggestions.append(
                    f"Falar com {prof_names} para perguntar se pode abrir disponibilidade em outro dia "
                    f"(sugestão de horários vagos na turma: {free_windows}), pois seus horários atuais "
                    f"já estão ocupados lecionando '{subjs_txt}'."
                )
            if other_clash:
                other_contacts = sorted({f"{a['professor']} ({a['subject']})" for a in other_clash})
                contacts_txt = ", ".join(other_contacts[:2])
                suggestions.append(
                    f"Ou falar com {contacts_txt} para verificar se pode mover sua aula para {free_windows}, "
                    f"liberando o horário para {prof_names}."
                )
            if not suggestions:
                suggestions.append(
                    f"Falar com {prof_names} para verificar se pode lecionar em {free_windows}."
                )
        else:
            suggestions.append(
                f"Falar com {prof_names} para verificar disponibilidade em {free_windows}."
            )

        return {
            "professor": prof_names,
            "reason": " ".join(sorted(reasons)) or "Sem combinação viável de horários disponíveis.",
            "suggestion": " ".join(suggestions),
        }

    def solve(self):
        t0 = pytime.perf_counter()

        initial_state = self.build_initial_solution()
        initial_cost = self.cost(initial_state)

        sa_improvements = 0
        ts_improvements = 0
        sa_cost = initial_cost

        if self.mode == "sa":
            best_state, final_raw_cost, sa_improvements = self.run_simulated_annealing(
                initial_state, use_tabu_memory=False
            )
            sa_cost = final_raw_cost
        elif self.mode == "tabu":
            best_state, final_raw_cost, ts_improvements = self.run_tabu_search(initial_state)
        else:
            sa_state, sa_cost, sa_improvements = self.run_simulated_annealing(
                initial_state, use_tabu_memory=True
            )
            best_state, final_raw_cost, ts_improvements = self.run_tabu_search(sa_state)

        elapsed_ms = round((pytime.perf_counter() - t0) * 1000, 1)

        metrics = {
            "algorithm": self.mode,
            "algorithm_label": {
                "hybrid": "Híbrido (Simulated Annealing + Tabu Search)",
                "sa": "Simulated Annealing",
                "tabu": "Tabu Search (Busca Tabu)",
            }[self.mode],
            "initial_cost": initial_cost,
            "sa_cost": sa_cost,
            "sa_improvements": sa_improvements,
            "ts_improvements": ts_improvements,
            "total_improvements": sa_improvements + ts_improvements,
            "elapsed_ms": elapsed_ms,
        }

        return self._sanitize_and_build_result(best_state, metrics)
