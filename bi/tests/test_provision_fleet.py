import importlib.util
from pathlib import Path

import pytest
import requests

spec = importlib.util.spec_from_file_location('provision_fleet', Path(__file__).parents[1] / 'metabase/provision_fleet.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_dashboard_cards_filters_and_layout_are_created_without_deleting_existing():
    class Response:
        def __init__(self, data): self.data = data
        def raise_for_status(self): pass
        def json(self): return self.data

    class Session:
        def __init__(self): self.posts = []; self.updates = []
        def post(self, url, json, timeout):
            self.posts.append((url,json))
            return Response({'id':len(self.posts)})
        def put(self, url, json, timeout):
            self.updates.append((url,json))
            return Response({})

    session = Session()
    assert module.provision('http://metabase', 2, 3, session) == 'http://metabase/dashboard/1'
    assert len(session.posts) == 8
    for url, card in session.posts[1:]:
        assert card['dataset_query']['database'] == 2
        assert card['collection_id'] == 3
        assert set(card['dataset_query']['native']['template-tags']) == {'family','location'}
    dashcards = session.updates[0][1]['dashcards']
    assert len(dashcards) == 7
    assert all(len(card['parameter_mappings']) == 2 for card in dashcards)
    assert all(card['col'] + card['size_x'] <= 24 for card in dashcards)


def test_http_errors_propagate_without_claiming_success():
    class Session:
        def post(self, *args, **kwargs):
            response = requests.Response()
            response.status_code = 403
            return response

    with pytest.raises(requests.HTTPError):
        module.provision('http://metabase',2,3,Session())
