"""SPARQL Query interface."""
#
# (C) Pywikibot team, 2016-2023
#
# Distributed under the terms of the MIT license.
#
from __future__ import annotations

from textwrap import fill
from urllib.parse import quote

from requests.exceptions import Timeout

from pywikibot import Site
from pywikibot.backports import removeprefix
from pywikibot.comms import http
from pywikibot.data import WaitingMixin
from pywikibot.exceptions import Error, NoUsernameError


try:
    from requests import JSONDecodeError
except ImportError:  # requests < 2.27.0
    from json import JSONDecodeError

DEFAULT_HEADERS = {'cache-control': 'no-cache',
                   'Accept': 'application/sparql-results+json'}


class SparqlQuery(WaitingMixin):
    """SPARQL Query class.

    This class allows to run SPARQL queries against any SPARQL endpoint.

    .. versionchanged:: 8.4
       inherited from :class:`data.WaitingMixin` which provides a
       :meth:`data.WaitingMixin.wait` method.
    """

    def __init__(self,
                 endpoint: str | None = None,
                 entity_url: str | None = None, repo=None,
                 max_retries: int | None = None,
                 retry_wait: float | None = None) -> None:
        """
        Create endpoint.

        :param endpoint: SPARQL endpoint URL
        :param entity_url: URL prefix for any entities returned in a query.
        :param repo: The Wikibase site which we want to run queries on. If
            provided this overrides any value in endpoint and entity_url.
            Defaults to Wikidata.
        :type repo: pywikibot.site.DataSite
        :param max_retries: (optional) Maximum number of times to retry after
               errors, defaults to config.max_retries.
        :param retry_wait: (optional) Minimum time in seconds to wait after an
               error, defaults to config.retry_wait seconds (doubles each retry
               until config.retry_max is reached).
        """
        # default to Wikidata
        if not repo and not endpoint:
            repo = Site('wikidata')

        if repo:
            try:
                self.endpoint = repo.sparql_endpoint
                self.entity_url = repo.concept_base_uri
            except NotImplementedError:
                raise NotImplementedError(
                    'Wiki version must be 1.28-wmf.23 or newer to '
                    'automatically extract the sparql endpoint. '
                    'Please provide the endpoint and entity_url '
                    'parameters instead of a repo.')
            if not self.endpoint:
                raise Error(
                    f'The site {repo} does not provide a sparql endpoint.')
        else:
            if not entity_url:
                raise Error('If initialised with an endpoint the entity_url '
                            'must be provided.')
            self.endpoint = endpoint
            self.entity_url = entity_url

        self.last_response = None

        if max_retries is not None:
            self.max_retries = max_retries
        if retry_wait is not None:
            self.retry_wait = retry_wait

    def get_last_response(self):
        """
        Return last received response.

        :return: Response object from last request or None
        """
        return self.last_response

    def select(self,
               query: str,
               full_data: bool = False,
               headers: dict[str, str] | None = None
               ) -> list[dict[str, str]] | None:
        """
        Run SPARQL query and return the result.

        The response is assumed to be in format defined by:
        https://www.w3.org/TR/2013/REC-sparql11-results-json-20130321/

        :param query: Query text
        :param full_data: Whether return full data objects or only values
        """
        if headers is None:
            headers = DEFAULT_HEADERS

        data = self.query(query, headers=headers)
        if not data or 'results' not in data:
            return None

        result = []
        qvars = data['head']['vars']
        for row in data['results']['bindings']:
            values = {}
            for var in qvars:
                if var not in row:
                    # var is not available (OPTIONAL is probably used)
                    values[var] = None
                elif full_data:
                    if row[var]['type'] not in VALUE_TYPES:
                        raise ValueError(f"Unknown type: {row[var]['type']}")
                    valtype = VALUE_TYPES[row[var]['type']]
                    values[var] = valtype(row[var],
                                          entity_url=self.entity_url)
                else:
                    values[var] = row[var]['value']
            result.append(values)
        return result

    def query(self, query: str, headers: dict[str, str] | None = None):
        """Run SPARQL query and return parsed JSON result.

        .. versionchanged:: 8.5
           :exc:``exceptions.NoUsernameError` is raised if the response
           looks like the user is not logged in.

        :param query: Query text
        :raises NoUsernameError: User not logged in
        """
        if headers is None:
            headers = DEFAULT_HEADERS

        # force cleared
        self.last_response = None

        url = f'{self.endpoint}?query={quote(query)}'
        while True:
            try:
                self.last_response = http.fetch(url, headers=headers)
                break
            except Timeout:
                self.wait()

        try:
            return self.last_response.json()
        except JSONDecodeError:
            # There is no proper error given but server returns HTML page
            # in case login isn't valid sotry to guess what the problem is
            # and notify user instead of silently ignoring it.
            # This could be made more reliable by fixing the backend.
            # Note: only raise error when response starts with HTML,
            # not in case the response otherwise might have it in between
            strcontent = self.last_response.content.decode()
            if (strcontent.startswith('<!DOCTYPE html>')
                and 'https://commons-query.wikimedia.org' in url
                and ('Special:UserLogin' in strcontent
                     or 'Special:OAuth' in strcontent)):
                raise NoUsernameError(fill(
                    'User not logged in. You need to log in to Wikimedia '
                    'Commons and give OAUTH permission. Open '
                    'https://commons-query.wikimedia.org with browser to '
                    'login and give permission.'
                ))
        return None

    def ask(self, query: str,
            headers: dict[str, str] | None = None) -> bool:
        """
        Run SPARQL ASK query and return boolean result.

        :param query: Query text
        """
        if headers is None:
            headers = DEFAULT_HEADERS
        data = self.query(query, headers=headers)
        return data['boolean']

    def get_items(self, query, item_name: str = 'item', result_type=set):
        """
        Retrieve items which satisfy given query.

        Items are returned as Wikibase IDs.

        :param query: Query string. Must contain ?{item_name} as one of the
            projected values.
        :param item_name: Name of the value to extract
        :param result_type: type of the iterable in which
              SPARQL results are stored (default set)
        :type result_type: iterable
        :return: item ids, e.g. Q1234
        :rtype: same as result_type
        """
        if res := self.select(query, full_data=True):
            return result_type(r[item_name].getID() for r in res)
        return result_type()


class SparqlNode:
    """Base class for SPARQL nodes."""

    def __init__(self, value) -> None:
        """Create a SparqlNode."""
        self.value = value

    def __str__(self) -> str:
        return self.value


class URI(SparqlNode):
    """Representation of URI result type."""

    def __init__(self, data: dict, entity_url, **kwargs) -> None:
        """Create URI object."""
        super().__init__(data.get('value'))
        self.entity_url = entity_url

    def getID(self):  # noqa: N802
        """
        Get ID of Wikibase object identified by the URI.

        :return: ID of Wikibase object, e.g. Q1234
        """
        if self.value.startswith(self.entity_url):
            return removeprefix(self.value, self.entity_url)
        return None

    def __repr__(self) -> str:
        return f'<{self.value}>'


class Literal(SparqlNode):
    """Representation of RDF literal result type."""

    def __init__(self, data: dict, **kwargs) -> None:
        """Create Literal object."""
        super().__init__(data.get('value'))
        self.type = data.get('datatype')
        self.language = data.get('xml:lang')

    def __repr__(self) -> str:
        if self.type:
            return f'{self.value}^^{self.type}'
        return f'{self.value}@{self.language}' if self.language else self.value


class Bnode(SparqlNode):
    """Representation of blank node."""

    def __init__(self, data: dict, **kwargs) -> None:
        """Create Bnode."""
        super().__init__(data.get('value'))

    def __repr__(self) -> str:
        return f'_:{self.value}'


VALUE_TYPES = {'uri': URI, 'literal': Literal, 'bnode': Bnode}
