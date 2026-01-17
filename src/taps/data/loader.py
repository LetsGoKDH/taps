"""
TAPS 데이터셋 로더

HuggingFace 데이터셋을 다운로드하고 로컬에 저장/로드하는 기능을 제공합니다.
"""

import os
from pathlib import Path
from datasets import load_dataset, load_from_disk, DatasetDict

# 기본 경로 설정
DEFAULT_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
DATASET_NAME = "yskim3271/Throat_and_Acoustic_Pairing_Speech_Dataset"
LOCAL_DATASET_PATH = DEFAULT_DATA_DIR / "taps_dataset"


def download_and_save(save_path: str = None) -> DatasetDict:
    """
    TAPS 데이터셋을 HuggingFace에서 다운로드하고 로컬에 저장합니다.

    Args:
        save_path: 저장할 경로 (기본값: ./data/taps_dataset)

    Returns:
        DatasetDict: 다운로드된 데이터셋

    사용 예시:
        >>> from taps.data import download_and_save
        >>> ds = download_and_save()
        데이터셋 다운로드 중...
        데이터셋 저장 완료: ./data/taps_dataset
    """
    if save_path is None:
        save_path = LOCAL_DATASET_PATH
    else:
        save_path = Path(save_path)

    # 폴더가 없으면 생성
    save_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"데이터셋 다운로드 중: {DATASET_NAME}")
    ds = load_dataset(DATASET_NAME)

    print(f"데이터셋 저장 중: {save_path}")
    ds.save_to_disk(str(save_path))

    print(f"완료! 저장 위치: {save_path}")
    print(f"  - Train: {len(ds['train'])} 샘플")
    print(f"  - Dev: {len(ds['dev'])} 샘플")
    print(f"  - Test: {len(ds['test'])} 샘플")

    return ds


def load_local(load_path: str = None) -> DatasetDict:
    """
    로컬에 저장된 TAPS 데이터셋을 불러옵니다.

    Args:
        load_path: 불러올 경로 (기본값: ./data/taps_dataset)

    Returns:
        DatasetDict: 로드된 데이터셋

    Raises:
        FileNotFoundError: 데이터셋이 로컬에 없는 경우

    사용 예시:
        >>> from taps.data import load_local
        >>> ds = load_local()
        >>> print(ds)
        DatasetDict({
            train: Dataset({...}),
            dev: Dataset({...}),
            test: Dataset({...})
        })
    """
    if load_path is None:
        load_path = LOCAL_DATASET_PATH
    else:
        load_path = Path(load_path)

    if not load_path.exists():
        raise FileNotFoundError(
            f"데이터셋을 찾을 수 없습니다: {load_path}\n"
            f"먼저 download_and_save()를 실행해서 데이터셋을 다운로드하세요."
        )

    print(f"로컬 데이터셋 로드 중: {load_path}")
    ds = load_from_disk(str(load_path))
    print(f"로드 완료!")

    return ds


def get_split(split: str = "train", load_path: str = None):
    """
    특정 split의 데이터셋만 불러옵니다.

    Args:
        split: 불러올 split ("train", "dev", "test")
        load_path: 불러올 경로 (기본값: ./data/taps_dataset)

    Returns:
        Dataset: 해당 split의 데이터셋

    사용 예시:
        >>> from taps.data import get_split
        >>> train_ds = get_split("train")
        >>> dev_ds = get_split("dev")
    """
    ds = load_local(load_path)

    if split not in ds:
        available = list(ds.keys())
        raise ValueError(f"'{split}'는 없는 split입니다. 사용 가능: {available}")

    return ds[split]


def is_dataset_downloaded(load_path: str = None) -> bool:
    """
    데이터셋이 로컬에 다운로드되어 있는지 확인합니다.

    Returns:
        bool: 다운로드 여부
    """
    if load_path is None:
        load_path = LOCAL_DATASET_PATH
    else:
        load_path = Path(load_path)

    return load_path.exists()


def load_from_hf_cache(hf_cache_dir: str = "D:/hf_cache") -> DatasetDict:
    """
    HuggingFace 캐시에서 직접 데이터셋을 로드합니다.

    save_to_disk()가 메모리 문제로 실패한 경우에도 이미 다운로드된
    HuggingFace 캐시에서 데이터셋을 로드할 수 있습니다.

    Args:
        hf_cache_dir: HuggingFace 캐시 디렉토리 (기본: D:/hf_cache)

    Returns:
        DatasetDict: 로드된 데이터셋

    사용 예시:
        >>> from taps.data import load_from_hf_cache
        >>> ds = load_from_hf_cache()
        >>> train = ds["train"]
    """
    cache_path = f"{hf_cache_dir}/datasets"
    os.makedirs(cache_path, exist_ok=True)

    print(f"HuggingFace 캐시에서 로드 중: {cache_path}")
    ds = load_dataset(DATASET_NAME, cache_dir=cache_path)

    print(f"로드 완료!")
    print(f"  - Train: {len(ds['train'])} 샘플")
    print(f"  - Dev: {len(ds['dev'])} 샘플")
    print(f"  - Test: {len(ds['test'])} 샘플")

    return ds


# CLI로 실행할 경우
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "download":
        download_and_save()
    else:
        print("사용법:")
        print("  python -m taps.data.loader download  # 데이터셋 다운로드")
        print("")
        print("또는 Python에서:")
        print("  from taps.data import download_and_save, load_local")
        print("  download_and_save()  # 처음 한 번만")
        print("  ds = load_local()    # 이후 로컬에서 로드")
