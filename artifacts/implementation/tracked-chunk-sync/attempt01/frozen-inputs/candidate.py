"""Exact hierarchy with an explicit new block-provider source identity."""
from hierarchical_store import HierarchicalStore as Original


class HierarchicalStore(Original):
    BLOCK_HASH = '81a65653fe163320216a177ad41576bc5dbe7efd7a2ce36297f1874fc9eeb30e'
