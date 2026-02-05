import pytest

from store.common.utils import ensure_cl_server_dir, get_db_url





pytestmark = pytest.mark.integration
def test_ensure_cl_server_dir_existing(tmp_path, monkeypatch):
    """Test ensure_cl_server_dir when the directory exists."""
    monkeypatch.setenv("CL_SERVER_DIR", str(tmp_path))

    cl_dir = ensure_cl_server_dir(create_if_missing=False)
    assert cl_dir == tmp_path
    assert cl_dir.exists()

def test_ensure_cl_server_dir_create(tmp_path, monkeypatch):
    """Test ensure_cl_server_dir when the directory does not exist and needs to be created."""
    new_dir = tmp_path / "cl_server_new"
    monkeypatch.setenv("CL_SERVER_DIR", str(new_dir))

    cl_dir = ensure_cl_server_dir(create_if_missing=True)
    assert cl_dir == new_dir
    assert cl_dir.exists()
    assert cl_dir.is_dir()

def test_ensure_cl_server_dir_missing_no_create(tmp_path, monkeypatch):
    """Test ensure_cl_server_dir raises SystemExit when missing and not creating."""
    new_dir = tmp_path / "cl_server_missing"
    monkeypatch.setenv("CL_SERVER_DIR", str(new_dir))

    with pytest.raises(SystemExit) as excinfo:
        ensure_cl_server_dir(create_if_missing=False)
    assert excinfo.value.code == 1

def test_ensure_cl_server_dir_not_set(monkeypatch):
    """Test ensure_cl_server_dir raises SystemExit when env var not set."""
    monkeypatch.delenv("CL_SERVER_DIR", raising=False)

    with pytest.raises(SystemExit) as excinfo:
        ensure_cl_server_dir()
    assert excinfo.value.code == 1

def test_get_db_url(tmp_path, monkeypatch):
    """Test get_db_url returns correct sqlite URL."""
    monkeypatch.setenv("CL_SERVER_DIR", str(tmp_path))

    db_url = get_db_url()
    assert db_url == f"sqlite:///{tmp_path}/store.db"
