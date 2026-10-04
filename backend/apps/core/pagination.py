"""
Configurable page size (Part 1).

Default DRF PageNumberPagination with a client-tunable page_size (capped
at 100). Needed so the guest cart can hydrate all of its lines in ONE
products request (?ids=…&page_size=N) instead of paging through the
whole catalog; harmless for every other list endpoint (they keep the
default PAGE_SIZE unless asked).
"""
from rest_framework.pagination import PageNumberPagination


class ConfigurablePageNumberPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 100
