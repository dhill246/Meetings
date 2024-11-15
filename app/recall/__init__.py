from flask import Blueprint

recall = Blueprint('recall', __name__)

from . import routes
