from rest_framework.pagination import PageNumberPagination


class OptionalPagination(PageNumberPagination):
    """Pagina só quando ?page= é enviado; sem ele, devolve a lista completa (usada em dropdowns e grades)."""
    page_size = 10
    def paginate_queryset(self, queryset, request, view=None):
        if self.page_query_param not in request.query_params: return None
        return super().paginate_queryset(queryset, request, view)
