from flask import Blueprint

stripe = Blueprint('stripe', __name__)

from . import routes
