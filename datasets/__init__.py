from .ml_20m import ML20MDataset
from .AnimeRatings import AnimeRatingsDataset

DATASETS = {
    ML20MDataset.code(): ML20MDataset,
    "AnimeRatings": AnimeRatingsDataset
}


def dataset_factory(args):
    dataset = DATASETS[args.dataset_code]
    return dataset(args)
