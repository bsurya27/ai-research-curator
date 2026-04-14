"""Preference vector load / save / online update."""

import io
import logging
import os
from pathlib import Path

import boto3
import numpy as np
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


def _s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION", "us-east-1"),
    )


def _is_s3() -> bool:
    return os.getenv("STORAGE_BACKEND", "local") == "s3"


S3_BUCKET = os.getenv("S3_BUCKET", "")

_DEFAULT_PATH = Path(__file__).resolve().parent / "data" / "preference.npy"


def _preference_path() -> Path:
    raw = os.getenv("PREFERENCE_PATH", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return _DEFAULT_PATH.resolve()


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n == 0.0:
        logger.error("zero vector cannot be normalized")
        raise ValueError("zero vector cannot be normalized")
    return v / n


def load_preference(dim: int) -> np.ndarray:
    """Load unit preference vector from disk, or random unit vector if missing."""
    if _is_s3():
        try:
            obj = _s3_client().get_object(Bucket=S3_BUCKET, Key="preference.npy")
            buf = io.BytesIO(obj["Body"].read())
            v = np.load(buf)
            v = np.asarray(v, dtype=np.float64).reshape(-1)
            if v.shape[0] != dim:
                raise ValueError(f"preference dim mismatch: got {v.shape[0]}, want {dim}")
            out = _unit(v)
            logger.info("loaded preference from s3://%s/preference.npy", S3_BUCKET)
            return out
        except Exception:
            pass  # any S3 read/parse failure → random init below
    else:
        path = _preference_path()
        if path.is_file():
            try:
                v = np.load(path)
                v = np.asarray(v, dtype=np.float64).reshape(-1)
                if v.shape[0] != dim:
                    logger.error("preference dim %d != expected %d", v.shape[0], dim)
                    raise ValueError(f"preference dim mismatch: got {v.shape[0]}, want {dim}")
                out = _unit(v)
                logger.info("loaded preference from %s", path)
                return out
            except Exception as e:
                logger.exception("load_preference failed: %s", e)
                raise
    v = np.random.randn(dim)
    out = _unit(v)
    logger.info("initialized random preference dim=%d", dim)
    return out


def save_preference(vector: np.ndarray) -> None:
    """Persist preference vector to ``PREFERENCE_PATH``."""
    if _is_s3():
        buf = io.BytesIO()
        np.save(buf, vector.astype(np.float64))
        buf.seek(0)
        try:
            _s3_client().put_object(Bucket=S3_BUCKET, Key="preference.npy", Body=buf.read())
            logger.info("saved preference to s3://%s/preference.npy", S3_BUCKET)
        except Exception as e:
            logger.exception("save_preference failed: %s", e)
            raise
    else:
        path = _preference_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            np.save(path, vector.astype(np.float64))
            logger.info("saved preference to %s", path)
        except Exception as e:
            logger.exception("save_preference failed: %s", e)
            raise


def update_preference(
    current: np.ndarray,
    item_embedding: list[float],
    signal: str,
    step_size: float = 0.1,
) -> np.ndarray:
    """Like/dislike update toward or away from item embedding; returns unit vector."""
    if signal not in ("like", "dislike"):
        logger.error("invalid signal: %s", signal)
        raise ValueError('signal must be "like" or "dislike"')
    item = np.asarray(item_embedding, dtype=np.float64).reshape(-1)
    if item.shape != current.shape:
        logger.error("embedding shape %s != current %s", item.shape, current.shape)
        raise ValueError("item_embedding dim mismatch")
    if signal == "like":
        new = current + step_size * (item - current)
    else:
        new = current - step_size * (item - current)
    return _unit(new)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    p = load_preference(8)
    print("load_preference shape", p.shape, "norm", float(np.linalg.norm(p)))
    p2 = update_preference(p, [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "like")
    print("after like", p2[:3])
