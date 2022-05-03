from skyfield.api import Topos, load
import datetime as dt
import time
from icalendar import Calendar, Event
import google_calendar

# rather than calculating eot at 12:00 GMT, this calculates the clock time (and so, eot) for solar noon/meridian (azimuth = 180 degrees)

gmt_eot_weekly_calendar_id = "prgqbrj080r4nb1091nsusl978@group.calendar.google.com"
pivot_dt = dt.datetime(2022,7,1,  12,0,0, tzinfo=dt.timezone.utc)
window_weeks = 26 # +/-this many weeks around the Sunday on/after the pivot (so window_weeks x 2 + 1 events in total)
anti_flood_s = 2 # delay between API calls to avoid flooding Google's API

def time_of_meridian_by_azim(date_dt):  # date_dt is a datetime
    # Andrew Hodgson method, iterating adjusting time until azimuth is due south
    eot_secs = 0 # start assuming eot = 0
    error_deg = 99 # ensure we go round the loop at least once
    iters = 0
    while abs(error_deg) >= 1/4800 : # 1/4800 : # 0.05s = 1/20 / (4 * 60) : get to within 0.05 sec
        iters += 1
        solar_noon_dt = date_dt + dt.timedelta(seconds = -eot_secs)
        sfdatetime = ts.utc(solar_noon_dt) # turn into a skyfield date
        sun_pos = greenwich.at(sfdatetime).observe(sun) # sun, seen from Greenwich on earth
        app_sun_pos = sun_pos.apparent() # calcualte az/el including speed of light, refraction, gravity, apparently!
        (_, az, _) = app_sun_pos.altaz() # get azimuth (type: angle) - discard elev and distance
        error_deg = 180 - az.degrees # positive for sun still slow (sun not yet bearing 180)
        eot_secs -= error_deg *4*60 # next guess: increment offset - for sun slow, solar noon will be later than clock time 
        # end of iteration loop
    eot_string = "+" if eot_secs>=0 else '-'
    eot_string += f"{int(abs(eot_secs)/60)}m {abs(eot_secs) % 60:.0f}s"
    print(f"By Azim:\t {solar_noon_dt.isoformat(sep=' ')}\t{eot_secs:10.3f}s\t{eot_string:10}", file=open('output.tsv', 'a'))
    return (solar_noon_dt, eot_string)


def time_of_meridian_by_transit(date_dt): # date_dt is a datetime
    # method taken from https://rhodesmill.org/skyfield/examples.html
    from skyfield import almanac
    from skyfield.api import wgs84, load

    midnight = date_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    next_midnight = midnight + dt.timedelta(days=1)

    ts = load.timescale()
    t0 = ts.from_datetime(midnight)
    t1 = ts.from_datetime(next_midnight)
    eph = load('de421.bsp')
    greenwich = wgs84.latlon(51.477928, 0.0)

    f = almanac.meridian_transits(eph, eph['Sun'], greenwich)
    times, events = almanac.find_discrete(t0, t1, f)
    times = times[events == 1]     # Select transits instead of antitransits.
    sun_at_meridian_dt = times[0].utc_datetime() # convert from skyfield Time to datetime
    eot_secs = (date_dt - sun_at_meridian_dt).total_seconds() # sun fast => positive sign
    eot_string = "+" if eot_secs>=0 else '-'
    eot_string += f"{int(abs(eot_secs)/60)}m {abs(eot_secs) % 60:.0f}s"
#    current_date = current_date.replace(tzinfo=dt.timezone.utc)
    print(f"By Transit:\t {sun_at_meridian_dt.isoformat(sep=' ')}\t{eot_secs:10.3f}s\t{eot_string:10}", file=open('output.tsv', 'a'))
    return (sun_at_meridian_dt, eot_string)

def make_ical_event(datetime, eot_string):
    event = Event()
    event.add('summary', f'EoT {eot_string}')
    event.add('dtstart', datetime)   # defaults to UTC (e.g. 20220630T120344Z) 
    event.add('dtend', datetime)
    return event

def create_gcal_event(service, timedate, summary, description):
    event = {
        'start' : {'dateTime': timedate, 'timeZone' : 'Europe/London'},
        'end' : {'dateTime': timedate, 'timeZone' : 'Europe/London'},
        'transparency' : 'transparent', # maps to not busy
        'colorId' : 3, # Banana
        'summary' : summary,
        'description' : description,
    }
    new_event = service.events().insert(calendarId=gmt_eot_weekly_calendar_id, body=event).execute()
    print(f"Gcal event created: {event}", file=open('output.tsv', 'a'))


print(f"\nEquation of Time Calendar Generator")
ts = load.timescale(builtin=True)
planets = load('de421.bsp')
earth, sun = planets['earth'], planets['sun']
esher = earth + Topos('51.3642523 N', '0.3583954 W')
greenwich = earth + Topos('51.477928 N', '0.0 W')

ical = Calendar()

gcal_service = google_calendar.calendar_login()

# now = dt.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
# google_calendar.create_event(gcal_service, now, 'Test event', 'This event was \nprogrammatically created!')
# google_calendar.create_event(gcal_service, '2022-05-03T12:00:00+00:00', 'Newly created event', 'This event was \nprogrammatically created!')


# calculate wanted window of wanted events window_start, window_end
# pull list of existing events in gmt eot calendar into current_list_dt
# delete any that are before or after the window
# calculate list of Sundays within the window
# identify any missing events and create them

print(f"Adjusting calendar to show Sundays within the window", file=open('output.tsv', 'w'))  # starts a new file, overwrites the old

# force pivot to be a Sunday
day_of_week = pivot_dt.weekday() # 0=Mon, 6=Sun
offset_to_sunday = 6-pivot_dt.weekday()
pivot_dt = pivot_dt + dt.timedelta(days=offset_to_sunday) # forced to a Sunday
window_start_dt = pivot_dt + dt.timedelta(days = -window_weeks*7) # also a Sunday
window_end_dt = pivot_dt + dt.timedelta(days = window_weeks*7) # also a Sunday

# now_zs = dt.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
window_end_zs = window_end_dt.isoformat()
window_start_zs = window_start_dt.isoformat()
print(f"window_start_zs \t{window_start_zs}", file=open('output.tsv', 'a'))
print(f"pivot_zs        \t{pivot_dt.isoformat()}", file=open('output.tsv', 'a'))
print(f"window_end_zs   \t{window_end_zs}", file=open('output.tsv', 'a'))

existing = [] # list of already in place entries
if True:
    # get all current entries in the calendar
    events_result = gcal_service.events().list(calendarId=gmt_eot_weekly_calendar_id, 
                                            singleEvents=True, orderBy='startTime').execute()
    for event in events_result.get('items', []):
        event_zs = event['start'].get('dateTime', event['start'].get('date')) # returns 'datetime' if exists, else 'date'
        if event_zs[:10] < window_start_zs[:10] or event_zs[:10] > window_end_zs[:10]: # ignore time, eot and timezone!
            action = 'Delete'
            print(f"Deleting event: {event_zs}, id: {event['id']}, {event['summary']}")
            gcal_service.events().delete(calendarId=gmt_eot_weekly_calendar_id, eventId=event['id']).execute()
            time.sleep(anti_flood_s) # avoid flooding Google's API
        else:
            action = 'Keep'
            existing.append(event_zs[:10]) # just the date string, no time or timezone
        print(f"{action}\t Event: {event_zs}, id: {event['id']}, {event['summary']}", file=open('output.tsv', 'a'))
    #    print(event, '\n') # dump entire dictionary

for i in range(0, (2 * window_weeks + 1) * 7, 7):  # step in weeks, starting on a Sunday
    date_dt = window_start_dt + dt.timedelta(days=i) # noon
    # Calculate EoT (two methods)
    (azim_iter_dt, eot_string) = time_of_meridian_by_azim(date_dt) # returns a datetime
    (meridian_dt, eot_string) = time_of_meridian_by_transit(date_dt) # returns a datetime
    ical.add_component(make_ical_event(meridian_dt, eot_string))

    #&&ToDo add location at Prime Meridian, Royal Observatory, Blackheath Ave, London SE10 8XJ, UK
    #&&ToDo set Not Busy (transparent vs opaque?)
    #&&ToDo set Yellow colour - see https://superuser.com/questions/1391210/how-can-i-add-color-to-events-in-the-ics-google-calendar-files
    #&&ToDo Set details to "Clock time of sun passing over prime meridian, Greenwich"

    # If this date is not in existing array, then call Google Calendar API to insert the event in calendar
    date_string = meridian_dt.isoformat(sep=' ')[:10] # just date part as string

    if date_string not in existing:
        print(f"Create {date_string}, EoT: {eot_string}")
        create_gcal_event(gcal_service, meridian_dt.isoformat(), f"EoT {eot_string}", "Sun is overhead the Prime Meridian")
        time.sleep(anti_flood_s) # avoid flooding the Google API
    else:
        print(f"Keep {date_string}, EoT: {eot_string}")
    # end of per-week loop

f = open('AH EoT weekly.ics', 'wb')
f.write(ical.to_ical())
f.close()

print(f"Fine.\n")
