# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2015-2018 CERN.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Invenio module for building and serving JSONSchemas."""

from __future__ import absolute_import, print_function

from flask import Blueprint, abort, current_app, jsonify, request
from jsonref import JsonRefError


def create_blueprint(state):
    """Create blueprint serving JSON schemas.

    :param state: :class:`invenio_jsonschemas.ext.InvenioJSONSchemasState`
        instance used to retrieve the schemas.
    """
    blueprint = Blueprint(
        'invenio_jsonschemas',
        __name__,
    )

    @blueprint.route('/<path:schema_path>')
    def get_schema(schema_path):
        """Retrieve a schema."""
        resolved = request.args.get(
            'resolved',
            current_app.config.get('JSONSCHEMAS_RESOLVE_SCHEMA'),
            type=int
        )

        with_refs = request.args.get(
            'refs',
            current_app.config.get('JSONSCHEMAS_REPLACE_REFS'),
            type=int
        ) or resolved

        schema = state.get_schema(
            schema_path,
            with_refs=with_refs,
            resolved=resolved
        )

        try:
            schema = jsonify(schema)
        except JsonRefError:
            abort(404)
        return schema

    return blueprint
