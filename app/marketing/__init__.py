from flask import Blueprint

marketing = Blueprint('marketing', __name__)

from . import routes
