import pytest
from fleetlab.models import make_database
from fleetlab.fixtures import seed


@pytest.fixture
def factory(tmp_path):
    engine, factory = make_database("sqlite:///" + str(tmp_path / "test.db"))
    with factory.begin() as db:
        seed(db)
    yield factory
    engine.dispose()
