# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2015-2018 CERN.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Invenio module for building and serving JSONSchemas."""

from __future__ import absolute_import, print_function

import json
import os

import pkg_resources
import six
from flask import abort, request
from flask_login import current_user
from jsonref import JsonRef
from six.moves.urllib.parse import urlsplit
from werkzeug.exceptions import HTTPException
from werkzeug.routing import Map, Rule
from werkzeug.utils import cached_property, import_string

from . import config
from .errors import JSONSchemaDuplicate, JSONSchemaNotFound
from .views import create_blueprint

try:
    from functools import lru_cache
except ImportError:
    from functools32 import lru_cache


class InvenioJSONSchemasState(object):
    """InvenioJSONSchemas state and api."""

    def __init__(self, app):
        """Constructor.

        :param app: application registering this state
        """
        self.app = app
        self.url_map = Map([Rule(
            '{0}/<path:path>'.format(self.app.config['JSONSCHEMAS_ENDPOINT']),
            endpoint='schema',
            host=self.app.config['JSONSCHEMAS_HOST'],
        )], host_matching=True)

    def get_schema(self, path, with_refs=False, resolved=False):
        """Retrieve a schema.

        :param path: schema's relative path.
        :param with_refs: replace $refs in the schema.
        :param resolved: resolve schema using the resolver
            :py:const:`invenio_jsonschemas.config.JSONSCHEMAS_RESOLVER_CLS`
        :raises invenio_jsonschemas.errors.JSONSchemaNotFound: If no schema
            was found in the specified path.
        :returns: The schema in a dictionary form.
        """

        @lru_cache(maxsize=1000)
        def wrapped(self, path, with_refs, resolved, user):
            """Wrapper for method to memoize results based on extra parameter: current_user."""
            try:
                schema = self.loader_cls()(self.path_to_url(path))
            except JSONSchemaNotFound:
                abort(404)

            if with_refs:
                schema = JsonRef.replace_refs(
                    schema,
                    base_uri=request.base_url,
                    loader=self.loader_cls() if self.loader_cls else None,
                )
            if resolved:
                schema = self.resolver_cls(schema)
            return schema

        return wrapped(self, path, with_refs, resolved, current_user)

    def list_schemas(self):
        """Deprecated.

        :returns: list of schema names.
        :rtype: list
        """
        return []

    def url_to_path(self, url):
        """Convert schema URL to path.

        :param url: The schema URL.
        :returns: The schema path or ``None`` if the schema can't be resolved.
        """
        parts = urlsplit(url)
        try:
            loader, args = self.url_map.bind(parts.netloc).match(parts.path)
            path = args.get('path')
            if loader == 'schema':
                return path
        except HTTPException:
            return None

    def path_to_url(self, path):
        """Build URL from a path.

        :param path: relative path of the schema.
        :returns: The schema complete URL or ``None`` if not found.
        """
        return self.url_map.bind(
            self.app.config['JSONSCHEMAS_HOST'],
            url_scheme=self.app.config['JSONSCHEMAS_URL_SCHEME']
        ).build(
            'schema', values={'path': path}, force_external=True)

    @cached_property
    def loader_cls(self):
        """Loader class used in `JsonRef.replace_refs`."""
        cls = self.app.config['JSONSCHEMAS_LOADER_CLS']
        if isinstance(cls, six.string_types):
            return import_string(cls)
        return cls

    @cached_property
    def resolver_cls(self):
        """Loader to resolve the schema."""
        cls = self.app.config['JSONSCHEMAS_RESOLVER_CLS']
        if isinstance(cls, six.string_types):
            return import_string(cls)
        return cls


class InvenioJSONSchemas(object):
    """Invenio-JSONSchemas extension.

    Register blueprint serving registered schemas and can be used as an api
    to register those schemas.

    .. note::

        JSON schemas are served as static files. Thus their "id" and "$ref"
        fields might not match the Flask application's host and port.
    """

    def __init__(self, app=None, **kwargs):
        """Extension initialization.

        :param app: The Flask application. (Default: ``None``)
        """
        self.kwargs = kwargs
        if app:
            self.init_app(app, **kwargs)

    def init_app(self, app, entry_point_group=None, register_blueprint=True,
                 register_config_blueprint=None):
        """Flask application initialization.

        :param app: The Flask application.
        :param entry_point_group: The group entry point to load extensions.
            (Default: ``invenio_jsonschemas.schemas``)
        :param register_blueprint: Register the blueprints.
        :param register_config_blueprint: Register blueprint for the specific
            app from a config variable.
        """
        self.init_config(app)

        if not entry_point_group:
            entry_point_group = self.kwargs['entry_point_group'] \
                if 'entry_point_group' in self.kwargs \
                else 'invenio_jsonschemas.schemas'

        state = InvenioJSONSchemasState(app)

        # Init blueprints
        _register_blueprint = app.config.get(register_config_blueprint)
        if _register_blueprint is not None:
            register_blueprint = _register_blueprint

        if register_blueprint:
            app.register_blueprint(
                create_blueprint(state),
                url_prefix=app.config['JSONSCHEMAS_ENDPOINT']
            )

        self._state = app.extensions['invenio-jsonschemas'] = state
        return state

    def init_config(self, app):
        """Initialize configuration."""
        for k in dir(config):
            if k.startswith('JSONSCHEMAS_'):
                app.config.setdefault(k, getattr(config, k))

        host_setting = app.config['JSONSCHEMAS_HOST']
        if not host_setting or host_setting == 'localhost':
            app.logger.warning('JSONSCHEMAS_HOST is set to {0}'.format(
                host_setting))

    def __getattr__(self, name):
        """Proxy to state object."""
        return getattr(self._state, name, None)


class InvenioJSONSchemasUI(InvenioJSONSchemas):
    """Invenio-JSONSchemas extension for UI."""

    def init_app(self, app):
        """Flask application initialization.

        :param app: The Flask application.
        """
        return super(InvenioJSONSchemasUI, self).init_app(
            app,
            register_config_blueprint='JSONSCHEMAS_REGISTER_ENDPOINTS_UI'
        )


class InvenioJSONSchemasAPI(InvenioJSONSchemas):
    """Invenio-JSONSchemas extension for API."""

    def init_app(self, app):
        """Flask application initialization.

        :param app: The Flask application.
        """
        return super(InvenioJSONSchemasAPI, self).init_app(
            app,
            register_config_blueprint='JSONSCHEMAS_REGISTER_ENDPOINTS_API'
        )
