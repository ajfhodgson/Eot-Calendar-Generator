from __future__ import print_function

import datetime
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar.events']
gmt_eot_calendar_id = "prgqbrj080r4nb1091nsusl978@group.calendar.google.com"

def calendar_login():
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # if this fails with 'Credentials Expired' simply 
            # DELETE C:\Users\andre\Google Drive\Sundials\EoT Calendar Generator\token.json
            # and re-run the file - it will be recreated.
            # &&ToDo - trap exception, delete the token.json file and tell user to run the program again
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    service = build('calendar', 'v3', credentials=creds)
    return service

def create_event(service, timedate, summary, description):
    event = {
        'start' : {'dateTime': timedate, 'timeZone' : 'Europe/London'},
        'end' : {'dateTime': timedate, 'timeZone' : 'Europe/London'},
        'summary' : summary,
        'description' : description,
    }
    new_event = service.events().insert(calendarId=gmt_eot_calendar_id, body=event).execute()

def main():
    """Modified from the Quickstart Example at https://developers.google.com/calendar/api/quickstart/python
    Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.
    """

    print("THIS IS JUST A TEST STUB - ARE YOU RUNNING THE WRONG FILE?")

    try:
        service = calendar_login()
        # Call the Calendar API
        now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        print('Getting upcoming events')
        events_result = service.events().list(calendarId=gmt_eot_calendar_id, timeMin=now,
                                              maxResults=2, singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])

        if not events:
            print('No upcoming events found.')
            return

        # Prints the start and name of the next 10 events
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            print(event, '\n')
            print(start, event['summary'], '\n\n')

        print("THIS IS JUST A TEST STUB - ARE YOU RUNNING THE WRONG FILE?")

    except HttpError as error:
        print('An error occurred: %s' % error)

if __name__ == '__main__':
    main()