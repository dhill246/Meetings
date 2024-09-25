
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
print(uri)

# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi(version="1", strict=True, deprecation_errors=True))


def get_prompts(org_name, org_id, type_name, user_id, collection_name="MeetingTypes"):

    print(f"Getting prompts for {org_name} with org_id {org_id} and type_name {type_name} and user_id {user_id}")

    database = client[org_name]

    collection = database[collection_name]

    try:
        result = collection.find({"type_name": type_name,
                                  "scope": "company_wide",
                               "org_id": org_id}).limit(1)[0]
                        
    except Exception as e:
        result = collection.find({"org_id": org_id}).limit(1)[0]
        

    try:

        result_2 = collection.find({"type_name": type_name,
                                  "scope": int(user_id),
                               "org_id": org_id}).limit(1)[0]
    
        
    except Exception as e:
        result_2 = {"personal_prompts": {}}

        print (f"Error: {e}")

    
    prompts = result["default_prompts"]

    prompts_2 = result_2["personal_prompts"]


    combined_prompt = prompts.copy()  # Make a copy to avoid modifying the original dict1
    combined_prompt.update(prompts_2)

    print(f"combined: {combined_prompt}")

    system_prompt = ""

    response_format = "Do not include any explanations, provide a RFC8259 compliant JSON response following this exact format:\n"

    for category in combined_prompt:

        description = combined_prompt[category]
        if category == "Initial Context":
            system_prompt += description + "\n"
        else:
            system_prompt += category + ": " + description + "\n"

            response_format += "{" + category + "} : " + "{your response}" + "\n"

    response_format += "If your response is multiple items, make them into a list, surrounded by square brackets, separated by commas.\n"

    return system_prompt, response_format

def add_meeting(org_name, org_id, raw_text, json_summary, attendees, meeting_duration, type_name, collection_name="Meeting"):
    logging.info(f"Adding meeting to {org_name} with org_id {org_id} and type_name {type_name}")

    database = client[org_name]
    collection = database[collection_name]

    utc_datetime = datetime.now()
    pacific = timezone("US/Mountain")
    local_datetime = pacific.localize(utc_datetime)

    collection.insert_one({
        "type_name": type_name,
        "org_id": org_id,
        "meeting_duration": meeting_duration,
        "attendees": attendees,
        "date": local_datetime,
        "raw_text": raw_text,
        "summary": json_summary
        })

def get_oneonone_meetings(meeting_type, org_name, org_id, attendee_info, collection_name="Meetings"):

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

def get_all_manager_meetings(org_name, org_id, attendee_info, collection_name="Meetings"):

    manager_id = attendee_info["manager_id"]

    database = client[org_name]
    collection = database[collection_name]
    
    results = collection.find({
        "org_id": org_id,
        "attendees": {
            "$elemMatch": {
                "user_id": manager_id,
                "role": "Manager"
            }
        }
    })

    return results

def get_all_employee_meetings(org_name, org_id, attendee_info, collection_name="Meetings"):

    employee_id = attendee_info["employee_id"]

    database = client[org_name]
    collection = database[collection_name]
    
    results = collection.find({
        "org_id": org_id,
        "attendees": {
            "$elemMatch": {
                "user_id": employee_id,
                "role": "Report"
            }
        }
    })

    return results

def get_all_employee_meetings(org_name, org_id, attendee_info, collection_name="Meetings"):

    employee_id = attendee_info["employee_id"]

    database = client[org_name]
    collection = database[collection_name]

    results = collection.find({
        "org_id": org_id,
        "attendees": {
            "$elemMatch": {
                "user_id": employee_id,
                "role": "Report"
            }
        }
    })

    return results


def get_one_on_ones(org_name, org_id, attendee_info, collection_name="Meetings"):

    manager_id = attendee_info["manager_id"]

    database = client[org_name]
    collection = database[collection_name]

    results = collection.find({
        "type_name": "One-on-One",
        "org_id": org_id,
        "attendees": {
            "$all": [
                {"$elemMatch": {"user_id": manager_id}},
                {"$elemMatch": {"role": "Manager"}}
            ]
        }
        })

    return results

# Get the number of meetings within the past month for a specific manager 
def get_meetings_last_month(org_name, org_id, id, role="Manager", days=30, collection_name="Meetings"):

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


def fetch_prompts(org_name, org_id, role, scope, collection_name="MeetingTypes"):
    database = client[org_name]
    collection = database[collection_name]

    result = collection.find({
        "org_id": org_id,
        "scope": scope,
        "access_level": "admin"
    })

    return list(result)
    
def update_prompts(org_name, org_id, role, prompt_id, updated_data, scope, collection_name="MeetingTypes"):
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


# Helper function to convert meeting duration from "Xh Xm Xs" to total seconds
def duration_to_seconds(duration_str):
    parts = duration_str.split()
    hours = int(parts[0].replace("h", ""))
    minutes = int(parts[1].replace("m", ""))
    seconds = int(parts[2].replace("s", ""))
    return hours * 3600 + minutes * 60 + seconds

def fetch_meeting_types(org_name, org_id, scope, collection_name="MeetingTypes"):
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
    

if __name__ == "__main__":

   prompts = fetch_prompts("BlenderProducts", 1, "Admin", scope=203)

   print(prompts)