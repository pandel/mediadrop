# This file is a part of MediaDrop (http://www.mediadrop.video),
# Copyright 2009-2018 MediaDrop contributors
# For the exact contribution history, see the git revision log.
# The source code contained in this file is licensed under the GPLv3 or
# (at your option) any later version.
# See LICENSE.txt in the main project directory, for more information.

from pylons import request

from mediadrop.controllers.api import get_order_by, require_api_key_if_necessary
from mediadrop.lib.base import BaseController
from mediadrop.lib.decorators import expose
from mediadrop.lib.helpers import url_for
from mediadrop.lib.thumbnails import thumb_url
from mediadrop.lib.xhtml import strip_xhtml
from mediadrop.model import Podcast

order_columns = {
    'id': Podcast.id,
    'slug': Podcast.slug,
}

class PodcastsController(BaseController):
    """
    JSON Podcast API
    """

    @expose('json')
    @require_api_key_if_necessary
    def index(self, order=None, offset=0, limit=10, **kwargs):
        """Query for a flat list of podcasts.

        :param order:
            A column name and 'asc' or 'desc', seperated by a space.
            Defaults to newest podcast first (id desc).
        :type order: str

        :param offset:
            Where in the complete resultset to start returning results.
            Defaults to 0, the very beginning. This is useful if you've
            already fetched the first 50 results and want to fetch the
            next 50 and so on.
        :type offset: int

        :param limit:
            Number of results to return in each query. Defaults to 10.
            The maximum allowed value defaults to 50 and is set via
            :attr:`request.settings['api_media_max_results']`.
        :type limit: int

        :param api_key:
            The api access key if required in settings
        :type api_key: unicode or None

        :rtype: JSON-ready dict
        :returns: The returned dict has the following fields:

            count (int)
                The total number of results that match this query.
            podcasts (list of dicts)
                A list of **podcast_info** dicts, as generated by the
                :meth:`_info <mediadrop.controllers.api.podcasts.PodcastsController._info>`
                method. The number of dicts in this list will be the lesser
                of the number of matched items and the requested limit.

        """
        query = Podcast.query

        if not order:
            order = 'id asc'

        query = query.order_by(get_order_by(order, order_columns))

        start = int(offset)
        limit = min(int(limit), int(request.settings['api_media_max_results']))

        # get the total of all the matches
        count = query.count()

        query = query.offset(start).limit(limit)

        return dict(
           podcasts = [self._info(p) for p in query.all()],
           count = count,
        )

    def _info(self, podcast):
        """Return a JSON-ready dict representing the given podcast instance.

        :rtype: JSON-Ready dict
        :returns: The returned dict has the following fields:

            id (int)
                The numeric unique identifier,
                :attr:`Podcast.id <mediadrop.model.categories.Category.id>`
            slug (unicode)
                The more human readable unique identifier,
                :attr:`Category.slug <mediadrop.model.categories.Category.slug>`
            name (unicode)
                The human readable
                :attr:`name <mediadrop.model.categories.Category.name>`
                of the category.
            parent (unicode or None)
                the :attr:`slug <mediadrop.model.categories.Category.slug>`
                of the category's parent in the hierarchy, or None.
            media_count (int)
                The number of media items that are published in this category,
                or in its sub-categories.

        """
        feed_url = url_for(controller='/podcasts', action='feed',
                           slug=podcast.slug, qualified=True)

        return dict(
            id = podcast.id,
            slug = podcast.slug,
            created_on = podcast.created_on.isoformat(),
            modified_on = podcast.modified_on.isoformat(),
            title = podcast.title or "",
            subtitle = podcast.subtitle or "",
            description = strip_xhtml(podcast.description),
            category = podcast.category,
            media_count = podcast.media_count_published,
            feed_url = feed_url,
            thumb_url = thumb_url(podcast, 'l', True),
        )