# jhbuild - a build script for GNOME 1.x and 2.x
# Copyright (C) 2001-2004  James Henstridge
#
#   httpcache.py: a simple HTTP cache
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

'''Very simple minded class that can be used to maintain a cache of files
downloaded from web servers.  It is designed to reduce load on web servers,
and draws ideas from feedparser.py.  Strategies include:
    - If a resource has been checked in the last 6 hours, consider it current.
    - support gzip transfer encoding.
    - send If-Modified-Since and If-None-Match headers when validating a
      resource to reduce downloads when the file has not changed.
    - honour Expires headers returned by server.  If no expiry time is
      given, it defaults to 6 hours.
'''

import os
import urllib2
import urlparse
import time
import rfc822
import StringIO
try:
    import gzip
except ImportError:
    gzip = None

try:
    import xml.dom.minidom
except ImportError:
    raise SystemExit, 'Python xml packages are required but could not be found'

def _parse_date(date):
    tm = rfc822.parsedate_tz(date)
    if tm:
        return rfc822.mktime_tz(tm)
    return 0

class CacheEntry:
    def __init__(self, uri, local, modified, etag, expires=0):
        self.uri = uri
        self.local = local
        self.modified = modified
        self.etag = etag
        self.expires = expires

class Cache:
    cachedir = os.path.join(os.environ['HOME'], '.jhbuild', 'cache')
    # default to a 6 hour expiry time.
    default_age = 6 * 60 * 60

    def __init__(self, cachedir=None):
        if cachedir:
            self.cachedir = cachedir
        if not os.path.exists(self.cachedir):
            os.makedirs(self.cachedir)
        self.entries = {}

    def read_cache(self):
        self.entries = {}
        cindex = os.path.join(self.cachedir, 'index.xml')
        try:
            document = xml.dom.minidom.parse(cindex)
        except:
            return # treat like an empty cache
        if document.documentElement.nodeName != 'cache':
            document.unlink()
            return # doesn't look like a cache

        for node in document.documentElement.childNodes:
            if node.nodeType != node.ELEMENT_NODE: continue
            if node.nodeName != 'entry': continue
            uri = node.getAttribute('uri')
            local = str(node.getAttribute('local'))
            if node.hasAttribute('modified'):
                modified = node.getAttribute('modified')
            else:
                modified = None
            if node.hasAttribute('etag'):
                etag = node.getAttribute('etag')
            else:
                etag = None
            expires = time.mktime(
                time.strptime(node.getAttribute('expires'),
                              '%Y-%m-%dT%H:%M:%S'))
            self.entries[uri] = CacheEntry(uri, local, modified, etag, expires)
        document.unlink()

    def write_cache(self):
        cindex = os.path.join(self.cachedir, 'index.xml')

        
        document = xml.dom.minidom.Document()
        document.appendChild(document.createElement('cache'))
        node = document.createTextNode('\n')
        document.documentElement.appendChild(node)
        for uri in self.entries.keys():
            entry = self.entries[uri]
            node = document.createElement('entry')
            node.setAttribute('uri', entry.uri)
            node.setAttribute('local', entry.local)
            if entry.modified:
                node.setAttribute('modified', entry.modified)
            if entry.etag:
                node.setAttribute('etag', entry.etag)
            node.setAttribute('expires',
                              time.strftime('%Y-%m-%dT%H:%M:%S',
                                            time.localtime(entry.expires)))
            document.documentElement.appendChild(node)

            node = document.createTextNode('\n')
            document.documentElement.appendChild(node)
        
        document.writexml(open(cindex, 'w'))
        document.unlink()

    def _make_filename(self, uri):
        '''picks a unique name for a new entry in the cache.
        Very simplistic.'''
        # get the basename from the URI
        parts = urlparse.urlparse(uri, allow_fragments=False)
        base = parts[2].split('/')[-1]
        if not base: base = 'index.html'

        is_unique = False
        while not is_unique:
            is_unique = True
            for uri in self.entries.keys():
                if self.entries[uri].local == base:
                    is_unique = False
                    break
            if not is_unique:
                base = base + '-'
        return base

    def load(self, uri, nonetwork=False):
        '''Downloads the file associated with the URI, and returns a local
        file name for contents.'''
        # pass file URIs straight through -- no need to cache them
        parts = urlparse.urlparse(uri)
        if parts[0] in ('', 'file'):
            return parts[2]

        now = time.time()

        # is the file cached and not expired?
        self.read_cache()
        entry = self.entries.get(uri)
        if entry:
            if nonetwork or now <= entry.expires:
                return os.path.join(self.cachedir, entry.local)

        if nonetwork:
            raise RuntimeError('file not in cache, but not allowed '
                               'to check network')

        request = urllib2.Request(uri)
        if gzip:
            request.add_header('Accept-encoding', 'gzip')
        if entry:
            if entry.modified:
                request.add_header('If-Modified-Since', entry.modified)
            if entry.etag:
                request.add_header('If-None-Match', entry.etag)

        try:
            response = urllib2.urlopen(request)

            # get data, and gunzip it if it is encoded
            data = response.read()
            if gzip and response.headers.get('Content-Encoding', '') == 'gzip':
                try:
                    data = gzip.GzipFile(fileobj=StringIO.StringIO(data)).read()
                except:
                    data = ''

            expires = response.headers.get('Expires')
            
            # add new content to cache
            entry = CacheEntry(uri, self._make_filename(uri),
                               response.headers.get('Last-Modified'),
                               response.headers.get('ETag'))
            filename = os.path.join(self.cachedir, entry.local)
            open(filename, 'wb').write(data)
        except urllib2.HTTPError, e:
            if e.code == 304: # not modified; update validated
                expires = e.hdrs.get('Expires')
                filename = os.path.join(self.cachedir, entry.local)
            else:
                raise

        # set expiry date
        entry.expires = _parse_date(expires)
        if entry.expires <= now: # ignore expiry times that have already passed
            entry.expires = now + self.default_age

        # save cache
        self.entries[uri] = entry
        self.write_cache()
        return filename

_cache = None
def load(uri, nonetwork=False):
    '''Downloads the file associated with the URI, and returns a local
    file name for contents.'''
    global _cache
    if not _cache: _cache = Cache()
    return _cache.load(uri, nonetwork=nonetwork)
