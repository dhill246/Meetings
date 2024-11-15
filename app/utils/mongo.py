from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import os
from datetime import datetime, timedelta
from pytz import timezone
from dotenv import load_dotenv
from bson import ObjectId
import logging

load_dotenv()

uri = os.getenv("MONGO_URI")

# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi(version="1", strict=True, deprecation_errors=True))

def get_prompts(org_name, org_id, type_name, user_id, collection_name="MeetingTypes"):
    """
    Get all meeting-types and prompts (company-wide) and user added meeting-types 
    and prompts if there are any.
    """
    
    print(f"Getting prompts for {org_name} with org_id {org_id} and type_name {type_name} and user_id {user_id}")

    database = client[org_name]
    collection = database[collection_name]

    result = {"default_prompts": {}}
    result_2 = {"default_prompts": {}}

    try:
        result = collection.find({"type_name": type_name, "scope": "company_wide", "org_id": org_id}).limit(1)[0]
    except IndexError:
        try:
            result = collection.find({"org_id": org_id}).limit(1)[0]
        except IndexError:
            print(f"No results found for org_id {org_id}")

    try:
        result_2 = collection.find({"type_name": type_name, "scope": int(user_id), "org_id": org_id}).limit(1)[0]
    except IndexError:
        print(f"No user-specific prompts found for user_id {user_id}")

    prompts = result.get("default_prompts", {})
    prompts_2 = result_2.get("default_prompts", {})

    combined_prompt = prompts.copy()
    combined_prompt.update(prompts_2)

    print(f"Combined Prompts: {combined_prompt}")

    system_prompt = ""
    categories = []  # New list to store categories

    for category, description in combined_prompt.items():
        if category == "Initial Context":
            system_prompt += description + "\n"
        else:
            system_prompt += f"{category}: {description}\n"
            categories.append(category)  # Store the category

    return system_prompt, categories

def add_meeting(org_name, org_id, raw_text, json_summary, attendees, meeting_duration, type_name, meeting_name, collection_name="Meeting"):
    """
    Add a meeting that has occured to Mongo database. This includes the raw text,
    summary in json format, attendees of the meeting, the duration of the meeting, 
    the type of meeting, and the name of the meeting.
    """

    logging.info(f"Adding meeting to {org_name} with org_id {org_id} and type_name {type_name}")

    database = client[org_name]
    collection = database[collection_name]

    utc_datetime = datetime.now()
    pacific = timezone("US/Mountain")
    local_datetime = pacific.localize(utc_datetime)

    collection.insert_one({
        "type_name": type_name,
        "meeting_name": meeting_name,
        "org_id": org_id,
        "meeting_duration": meeting_duration,
        "attendees": attendees,
        "date": local_datetime,
        "raw_text": raw_text,
        "summary": json_summary
        })

def get_oneonone_meetings(meeting_type, org_name, org_id, attendee_info, collection_name="Meetings"):
    """
    Get all one-on-one meetings between a specific manager and specific employee.
    """

    manager_id = attendee_info["manager_id"]
    report_id = attendee_info["report_id"]

    database = client[org_name]
    collection = database[collection_name]

    results = collection.find({
        "type_name": meeting_type,
        "org_id": org_id,
        "attendees": {
            "$all": [
                {"$elemMatch": {"user_id": manager_id}},
                {"$elemMatch": {"user_id": report_id}}
            ]
        }
        })

    return results

def get_all_employee_meetings(org_name, org_id, days, attendee_info, collection_name="Meetings"):
    """
    Get all one-on-one meetings with a specific employee as a direct report
    within the last 'days' days, returning only specific fields.
    """

    employee_id = attendee_info["employee_id"]
    
    # Calculate the cutoff date
    cutoff_date = datetime.now() - timedelta(days=days)

    # Connect to the database and collection
    database = client[org_name]
    collection = database[collection_name]
    
    # Query with both the attendee and date filter, using a projection
    results = collection.find(
        {
            "org_id": org_id,
            "attendees": {
                "$elemMatch": {
                    "user_id": employee_id,
                    "role": "Report"
                }
            },
            "date": {
                "$gte": cutoff_date
            }
        },
        {
            "type_name": 1,
            "meeting_duration": 1,
            "attendees": 1,
            "date": 1,
            "raw_text": 1,
            "summary": 1
        }
    )

    return list(results)

def get_employee_meetings_for_chat(org_name, org_id, days, attendee_info, collection_name="Meetings"):
    """
    Get all one-on-one meetings with a specific employee as a direct report
    within the last 'days' days, returning only specific fields.
    """

    employee_id = attendee_info["employee_id"]
    
    # Calculate the cutoff date
    cutoff_date = datetime.now() - timedelta(days=days)

    # Connect to the database and collection
    database = client[org_name]
    collection = database[collection_name]
    
    # Query with both the attendee and date filter, using a projection
    results = collection.find(
        {
            "org_id": org_id,
            "attendees": {
                "$elemMatch": {
                    "user_id": employee_id,
                    "role": "Report"
                }
            },
            "date": {
                "$gte": cutoff_date
            }
        },
        {
            "type_name": 1,
            "meeting_duration": 1,
            "attendees": 1,
            "date": 1,
            "raw_text": 1,
            "summary": 1
        }
    )

    return list(results)

def get_all_manager_meetings(org_name, org_id, days, attendee_info, collection_name="Meetings"):
    """
    Get all meetings held by a specific manager, regardless of type, within the last 'days' days,
    returning only specific fields.
    """
    print(f"Getting manager meetings for org {org_name}, org id {org_id}, from now to {days} ago, with attendees {attendee_info}")

    manager_id = attendee_info["manager_id"]
    
    # Calculate the cutoff date
    cutoff_date = datetime.now() - timedelta(days=days)
    print(cutoff_date)

    # Connect to the database and collection
    database = client[org_name]
    collection = database[collection_name]
    
    # Query with both the attendee and date filter, using a projection
    results = collection.find(
        {
            "org_id": org_id,
            "attendees": {
                "$elemMatch": {
                    "user_id": manager_id,
                    "role": "Manager"
                }
            },
            "date": {
                "$gte": cutoff_date
            }
        },
        {
            "type_name": 1,
            "meeting_duration": 1,
            "summary": 1,
            "attendees": 1,
            "date": 1,
            "raw_text": 1
        }
    )

    return list(results)

def get_meetings_for_chat(org_name, org_id, days, manager_id_list, report_id_list, collection_name="Meetings", type_name="One-on-One"):
    """
    Get all meetings held by a specific manager, regardless of type, within the last 'days' days,
    returning only specific fields.
    """

    # Calculate the cutoff date
    cutoff_date = datetime.now() - timedelta(days=days)

    # Connect to the database and collection
    database = client[org_name]
    collection = database[collection_name]
    
   
    # Base query for filtering by organization, meeting type, and date range
    query = {
        "org_id": org_id,
        "type_name": "One-on-One",
        "date": {"$gte": cutoff_date}
    }

    # Adjust query to handle cases where one of the lists is empty
    attendees_criteria = []
    if manager_id_list:
        attendees_criteria.append({
            "$elemMatch": {
                "user_id": {"$in": manager_id_list},
                "role": "Manager"
            }
        })
    if report_id_list:
        attendees_criteria.append({
            "$elemMatch": {
                "user_id": {"$in": report_id_list},
                "role": "Report"
            }
        })

    # Only add the attendees filter if criteria exist
    if attendees_criteria:
        query["attendees"] = {"$all": attendees_criteria}

    # Query the collection with the constructed query and projection
    results = collection.find(
        query,
        {
            "type_name": 1,
            "meeting_duration": 1,
            "summary": 1,
            "attendees": {"first_name": 1,
                "last_name": 1,
                "role": 1},
            "date": 1,
            "raw_text": 1
        }
    )

    # Convert results to a list and remove duplicates by using a set of `_id`s
    unique_meetings = {meeting["_id"]: meeting for meeting in results}

    return list(unique_meetings.values())

def get_one_on_ones(org_name, org_id, attendee_info, collection_name="Meetings"):
    """
    Get all of a manager's one-on-one meetings with all employees
    """

    manager_id = attendee_info["manager_id"]

    database = client[org_name]
    collection = database[collection_name]

    results = collection.find({
        "type_name": "One-on-One",
        "org_id": org_id,
        "attendees": {
            "$elemMatch": {
            "user_id": manager_id,
            "role": "Manager"
        }
        }
        })

    return results


# Get the number of meetings within the past month for a specific manager 
def get_meetings_last_month(org_name, org_id, id, role="Manager", days=30, collection_name="Meetings"):
    """
    Get all meetings for a specific manager or employee within the past month.
    """

    database = client[org_name]
    collection = database[collection_name]
    # Calculate the date for one month ago
    one_month_ago = datetime.now() - timedelta(days=days)
    print(one_month_ago)


    # Query to find meetings with the manager's user_id in attendees array and date within the past month
    results = collection.find({
        "type_name": "One-on-One",
        "org_id": org_id,
        "attendees": {
            "$elemMatch": {
                "user_id": id,
                "role": role
            }
        },
        "date": {"$gte": one_month_ago}
    })

    return list(results)


def get_meeting_by_id(org_name, org_id, meeting_id, collection_name="Meetings"):
    """
    Get a specific meeting by it's id in the database.
    """

    database = client[org_name]
    collection = database[collection_name]

    try:
        # Convert meeting_id to ObjectId
        meeting_object_id = ObjectId(meeting_id)
    except Exception as e:
        raise ValueError(f"Invalid meeting ID format: {e}")

    result = collection.find_one({
        "org_id": org_id,
        "_id": meeting_object_id
    })

    return result

def fetch_prompts(org_name, org_id, scope, collection_name="MeetingTypes"):
    """
    Fetches all prompts for a specific scope, either company-wide (everyone can see)
    or personal (scope is user_id and only current user can see)
    """

    database = client[org_name]
    collection = database[collection_name]

    result = collection.find({
        "org_id": org_id,
        "scope": scope,
    })

    return list(result)
    
def update_prompts(org_name, org_id, role, prompt_id, updated_data, scope, collection_name="MeetingTypes"):
    """
    Update company-wide prompts if scope is company-wide, or a specific user prompt
    if scope is user_id.
    """

    database = client[org_name]
    collection = database[collection_name]

    query_filter = {
        "org_id": org_id,
        "_id": ObjectId(prompt_id),
        "scope": scope
    }

    update_operation = {
        "$set": updated_data
    }

    if role == "admin":

        result = collection.update_one(query_filter, update_operation)

        return result

def duration_to_seconds(duration_str):
    """
    Helper function to convert meeting duration from "Xh Xm Xs" to total seconds
    """
    
    parts = duration_str.split()
    hours = int(parts[0].replace("h", ""))
    minutes = int(parts[1].replace("m", ""))
    seconds = int(parts[2].replace("s", ""))
    return hours * 3600 + minutes * 60 + seconds

def fetch_meeting_types(org_name, org_id, scope, collection_name="MeetingTypes"):
    """
    Get all available meeting types as a list
    """

    # TODO - This can be simplified without requesting all this data.

    database = client[org_name]
    collection = database[collection_name]

    result = collection.find({
            "org_id": org_id,
            "$or": [
                {"scope": "company_wide"},
                {"scope": scope}
            ]
        })
    
    return [result["type_name"] for result in result]

def get_general_meetings(meeting_type, org_name, org_id, attendee_info, collection_name="Meetings"):

    database = client[org_name]
    collection = database[collection_name]

    results = collection.find({
        "type_name": meeting_type,
        "org_id": org_id,
        "attendees": {
            "$elemMatch": attendee_info
        }
    })

    return results

def add_new_meeting_type(org_name, org_id, role, meeting_type_data, scope="company_wide", collection_name="MeetingTypes"):
    database = client[org_name]
    collection = database[collection_name]

    print(meeting_type_data)

    # Check if a meeting type with the same name already exists
    existing_meeting_type = collection.find_one({
        "org_id": org_id,
        "type_name": meeting_type_data.get("type_name"),
        "scope": scope
    })

    if existing_meeting_type:
        query_filter = {
            "org_id": org_id,
            "type_name": meeting_type_data.get("type_name"),
            "scope": scope
        }

        update_operation = {
            "$set": meeting_type_data
        }

        result = collection.update_one(query_filter, update_operation)
        return {"updated": True, "result": result}

    meeting_type_data["org_id"] = org_id
    meeting_type_data["scope"] = scope
    meeting_type_data["access_level"] = role
    result = collection.insert_one(meeting_type_data)

    return result


def fetch_personal_prompts(org_name, org_id, role, collection_name="MeetingTypes", scope="personal"):
    database = client[org_name]
    collection = database[collection_name]

    result = collection.find({
            "org_id": org_id,
            "scope": scope,
            "$or": [
                {"access_level": "manager"},
                {"access_level": role}
            ]
        })
    
    return list(result)


def delete_prompts(org_name, org_id, role, prompt_id, scope, collection_name="MeetingTypes"):
    database = client[org_name]
    collection = database[collection_name]

    query_filter = {
        "org_id": org_id,
        "_id": ObjectId(prompt_id),
        "scope": scope
    }
    
    result = collection.delete_one(query_filter)

    return result
    

def get_meeting_data(org_name, org_id, meeting_id, collection_name="Meetings"):

    database = client[org_name]
    collection = database[collection_name]

    result = collection.find_one({
        "org_id": org_id, 
        "_id": ObjectId(meeting_id)
    })

    return result

def get_all_one_on_ones(org_name, org_id, report_id, collection_name="Meetings"):

    database = client[org_name]
    collection = database[collection_name]

    result = collection.find({
        "org_id": org_id,
        "type_name": "One-on-One", 
        "attendees": {
            "$elemMatch": {
                "role": "Report",
                "user_id": report_id
            }}
    })

    return list(result)

def get_recent_meetings(org_name, org_id, meeting_type, limit=10, collection_name="Meetings"):
    database = client[org_name]
    collection = database[collection_name]

    result = collection.find({
        "org_id": org_id,
        "type_name": meeting_type,
         "raw_text": {"$exists": True}
    }).sort("date", -1).limit(limit)  # Sort by 'meeting_date' in descending order and limit to 10

    return list(result)

def update_document_with_raw_text(org_name, document_id, raw_text, collection_name="Meetings"):
    database = client[org_name]
    collection = database[collection_name]

    result = collection.update_one(
        {"_id": ObjectId(document_id)},  # Use ObjectId to query the _id field
        {"$set": {"raw_text": raw_text}}  # Update or add the 'raw_text' field
    )
    
    if result.matched_count > 0:
        print(f"Document with id {document_id} was successfully updated.")
    else:
        print(f"No document found with id {document_id}.")

def update_notes(org_name, document_id, notes, collection_name="Meetings"):
    database = client[org_name]
    collection = database[collection_name]

    result = collection.update_one(
        {"_id": ObjectId(document_id)},  # Use ObjectId to query the _id field
        {"$set": {"summary.Notes": notes}}  # Update or add the 'Notes' field within 'summary'
    )

    if result.modified_count > 0:
        print(f"Successfully updated document with id {document_id}.")
    else:
        print(f"No document found with id {document_id} or no update needed.")


def delete_meeting(org_name, org_id, meeting_id, role, collection_name="Meetings"):
    """
    Delete a meeting from the MongoDB collection.
    
    :param org_name: Name of the organization (used as the database name)
    :param org_id: ID of the organization
    :param meeting_id: ObjectId of the meeting to delete
    :param role: Role of the user requesting deletion (must be admin)
    :param collection_name: MongoDB collection name (default is 'Meetings')
    :return: Deletion result
    """
    database = client[org_name]  # Access the organization's database
    collection = database[collection_name]

    query_filter = {
        "org_id": org_id,
        "_id": meeting_id  # Filter by the meeting's ObjectId
    }

    if role == "admin":
        # Perform deletion
        result = collection.delete_one(query_filter)
        return result
    else:
        logging.error("User does not have permission to delete meetings")
        return None
    

def mongo_org_setup(org_name, org_id):

    # Get demo organization meeting types for copying to the new database
    source_db = client["DemoOrganization"]
    source_type_collection = source_db["MeetingTypes"]

    # Setup new database and collections
    new_db = client[org_name]
    new_meeting_collection = new_db.create_collection("Meetings")
    new_type_collection = new_db.create_collection("MeetingTypes")

    # Get documents to transfer   
    documents = list(source_type_collection.find())

        # Update the org_id field in each document
    for doc in documents:
        doc["org_id"] = org_id  # Replace the org_id with the new value
        # Remove the "_id" field to avoid duplicate key errors if not desired in the new collection
        if "_id" in doc:
            del doc["_id"]

    if documents:
        new_type_collection.insert_many(documents)

        print(f"Inserted {len(documents)} documents into {new_type_collection.name}")
    else:
        print("No documents found in the source collection.")

    
    return "success"


    

if __name__ == "__main__":
   
    my_list = get_all_employee_meetings("DemoOrganization", 999, 365,  {"employee_id": 1001})

    print(my_list)
