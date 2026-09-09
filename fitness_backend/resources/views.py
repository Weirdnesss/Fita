from rest_framework import generics

from .models import Resource
from .serializers import ResourceSerializer


class ResourceListView(generics.ListAPIView):
    """
    GET /resources/?category=workout&q=beginner
    Global read-only catalog (like nutrition's FoodSearchView) -- not
    scoped to the requesting user, since this is curated content
    everyone sees the same list of.
    """

    serializer_class = ResourceSerializer

    def get_queryset(self):
        qs = Resource.objects.all()
        category = self.request.query_params.get("category", "").strip()
        if category:
            qs = qs.filter(category=category)
        q = self.request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(title__icontains=q)
        return qs
