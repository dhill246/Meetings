
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import os
from datetime import datetime
from pytz import timezone
from dotenv import load_dotenv

load_dotenv()

uri = os.getenv("MONGO_URI")
print(uri)

# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi(version="1", strict=True, deprecation_errors=True))

def add_meeting(client_name, collection_name, attendees, raw_text, summary):

    client = client[client_name]

    collection = client[collection_name]

    utc_datetime = datetime.now()
    pacific = timezone("US/Mountain")
    local_datetime = pacific.localize(utc_datetime)

    collection.insert_one({
        "type_name": "One-on-One",
        "date": local_datetime,
        "attendees": attendees,
        "raw_text": raw_text,
        "summary": {
            "Meeting Summary": """The meeting focused on the need for strategic planning and resource allocation for the
                            upcoming year, particularly in terms of targeting and working with specific representatives.
                            There was also a discussion about the effectiveness of current representatives and the need
                            for more experienced personnel to handle field support and travel.""",
            "Action Items": [
                "Identify Targeted Representatives: Develop a plan to work with targeted representatives for the year.",
                "Field Support and Travel: Assign an experienced engineer to handle field support and travel.",
                "Rep Council Participation: Reevaluate the participants in the rep council to ensure the right people are involved.",
                "Budget Planning: Finalize the budget, considering the addition of new hires and the impact on overall labor costs.",
                "Follow-Up with Reps: Contact Charlie to discuss the need for leadership participation from SVL and possibly other organizations."
            ],
            "Takeaways": [
                "There is a need for more experienced personnel to handle field support and travel.",
                "The current rep council may not have the right individuals for effective feedback and strategy development.",
                "Budget increases are primarily due to new hires, which are seen as necessary investments for growth.",
                "The importance of being more present and engaged with reps to drive business growth was emphasized.",
            ],
            "Notable Moments": [
                "Brent Danielson's criticism of Texas Air Systems and Jim Hart highlighted a potential maturity issue and the need for better understanding and learning from industry leaders.",
                "The discussion about the effectiveness of different reps and the need for leadership participation in the rep council was a key point.",
                "The conversation about balancing execution work with business development underscored the need for a more strategic approach to resource allocation."
            ]
        }
    })