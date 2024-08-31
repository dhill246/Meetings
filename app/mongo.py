
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import os

uri = os.getenv("MONGO_URI")

# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi('1'))

# Create a database for testing
database = client["test_database"]

# Create a collection for testing
# database.create_collection("example_collection")

# List all collections in the database
collection = database["example_collection"]

# # Add some data to the collection
# document_list = [
#    { "name" : "Mongo's Burgers" },
#    { "name" : "Mongo's Pizza" }
# ]

# collection.insert_many(document_list)

results = list(collection.find({'name': "Mongo's Burgers"}))

print(results)

# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    # print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)