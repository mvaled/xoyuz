#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#----------------------------------------------------------------------
# xoyuz.utils
#----------------------------------------------------------------------
# Copyright (c) 2013-2014 Merchise Autrement and Contributors
# All rights reserved.
#
# Author: Eddy Ernesto del Valle Pino <eddy@merchise.org>
# Contributors: see CONTRIBUTORS and HISTORY file
#
# This is free software; you can redistribute it and/or modify it under the
# terms of the LICENCE attached (see LICENCE file) in the distribution
# package.


from __future__ import (
    absolute_import as _py3_abs_imports,
    division as _py3_division,
    print_function as _py3_print,
    unicode_literals as _py3_unicode
)

import re
import posixpath
from shutil import move
from os.path import join, splitext, dirname
from hashlib import sha1
try:
    from urllib.parse import unquote
except ImportError:     # Python 2
    from urllib import unquote

from xoutil.decorator import memoized_property
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.files.storage import default_storage


url_pattern = re.compile(r'url\(["\']?[^"\'\)]*[\'"]?\)')
url_extractor = re.compile(r'url\(["\']?(?P<url>[^"\'\)]*)[\'"]?\)')

JS_EXTENSION = '.js'
CSS_EXTENSION = '.css'


class Bundle(object):
    def __init__(self, paths):
        self.paths = paths
        name, ext = splitext(paths[0])
        if ext == JS_EXTENSION:
            self.language = 'javascript'
            self.ext = '.js'
        elif ext == CSS_EXTENSION:
            self.language = 'stylesheet'
            self.ext = '.css'
        else:
            raise ValueError('Unknown file type: ' + paths)

    @memoized_property
    def file_name(self):
        joined_paths = ''.join(self.paths)
        return sha1(joined_paths).hexdigest() + self.ext

    @memoized_property
    def file_path(self):
        return join('resources', self.file_name)

    @property
    def url(self):
        if not default_storage.exists(self.file_path):
            self.compile_assets()
        return default_storage.url(self.file_path)

    def compile_assets(self):
        file_content = FileContent(self.file_path)
        for path in self.paths:
            normalized_path = posixpath.normpath(unquote(path)).lstrip('/')
            fs_path = finders.find(normalized_path)
            if fs_path is None:
                raise ValueError('File not found "%s"' % normalized_path)
            else:
                content = open(fs_path).read()
            file_content.append(content, path)

        real_path = default_storage.save(
            self.file_path,
            file_content
        )
        if real_path != self.file_path:
            move(
                default_storage.path(real_path),
                default_storage.path(self.file_path)
            )


class FileContent(object):
    def __init__(self, path):
        self._is_css = path.endswith('.css')
        self._is_minified = False
        self.content = []

    def append(self, chunk, path):
        """Append static resources to this file."""
        if self._is_css:
            chunk = self.adjust_urls(chunk, path)
        self.content.append(chunk.decode('utf8'))

    def minify(self):
        if not self._is_minified:
            if self._is_css:
                from cssmin import cssmin

                def minify(css):
                    """Revert `box-shadow`, webkit does not understands it."""
                    css = cssmin(css)
                    css = css.replace('box-shadow:0;', 'box-shadow:0 0;')
                    return css

            else:
                from jsmin import jsmin as minify
            all_content = ''.join(self.content)
            self.content = minify(all_content).encode('utf8')
            self._is_minified = True

    def chunks(self):
        """Minify the content of the file before yielding it."""
        self.minify()
        yield self.content

    def adjust_urls(self, file_content, path):
        """Translate the URLs in a CSS file to absolute URLs."""
        file_content = file_content.decode('utf8')
        replacements = {}
        for url_ref in url_pattern.findall(file_content):
            url = url_extractor.match(url_ref).groups()[0]
            path_dirname = dirname(path)
            if path_dirname:
                path_dirname += '/'
            replacements[url_ref] = 'url("../..%s%s%s")' % (
                settings.STATIC_URL, path_dirname, url
            )
        for old, new in replacements.iteritems():
            file_content = file_content.replace(old, new)
        return file_content.encode('utf8')


def get_tags(urls):
    """Take static resource address and return the appropriate HTML tag."""
    tags = []
    for url in urls:
        name, ext = splitext(url)
        if ext == JS_EXTENSION:
            tag = '<script src="%s.js"></script>'
        else:
            tag = '<link href="%s.css" rel="stylesheet">'
        tags.append(tag % name)
    return '\n'.join(tags)
