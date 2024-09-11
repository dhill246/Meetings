# from app.models import db

# def create_meeting(manager_id, report_id, organization_id, s3_summary_name):
#     print("CREATING THE MEETING")
#     # Check if a similar meeting already exists
#     existing_meeting = Meeting.query.filter_by(
#         manager_id=manager_id,
#         report_id=report_id,
#         organization_id=organization_id,
#         s3_summary_name=s3_summary_name
#     ).first()

#     if existing_meeting:
#         pass

#     else:
    
#         # Create a new meeting instance
#         new_meeting = Meeting(
#             manager_id=manager_id,
#             report_id=report_id,
#             organization_id=organization_id,
#             s3_summary_name=s3_summary_name,
#         )

#         # Add the new meeting to the session
#         db.session.add(new_meeting)

#         # Commit the session to save the meeting to the database
#         db.session.commit()