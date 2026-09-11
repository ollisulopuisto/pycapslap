from app.core_client import CoreClient


def test_core_client_check_model_exists(qapp):
    client = CoreClient()
    try:
        fut = client.call("checkModelExists", "tiny")
        result = fut.result(timeout=5.0)
        assert isinstance(result, bool)
    finally:
        client.close()


def test_core_client_extract_first_frame(qapp):
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    sample = str((repo_root / "rust" / "bin" / "test_input.mp4").resolve())
    client = CoreClient()
    try:
        fut = client.call("extractFirstFrame", {"videoPath": sample})
        result = fut.result(timeout=10.0)
        assert "imageData" in result
        data = result["imageData"]
        assert data.startswith("data:image/")
    finally:
        client.close()
