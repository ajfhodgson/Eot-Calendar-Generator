from skyfield.api import Topos, load
import datetime as dt
import time
from icalendar import Calendar, Event
import google_calendar

# This program calculates the equation of time for a series of dates, and creates calendar events for those times/dates 
# showing EoT and the sun's declination
# It calculates EoT for the 'window_weeks' weeks either side of 'pivot_dt'
# Strinctly, it calculates EoT for every Sunday within 'window_weeks' weeks either side of the first Sunday on/after 'pivot_dt'
# It creates an ical file containing these events
# It manages a Google calendar 'gmt_eot_weekly_calendar_id' to reflect these events:
#   it deletes all events in the calendar outside the window range, leaving events inside the window range alone
#   it checks that there is an existing event for each calculated Sunday, if not, it creates a new event
# The time of the event is the minute when the sun is overhead Greenwich meridian (i.e. solar noon at the prime meridian)
# rather than calculating the EoT for 12:00 GMT on that day.

gmt_eot_weekly_calendar_id = "prgqbrj080r4nb1091nsusl978@group.calendar.google.com"
pivot_dt = dt.datetime(2022,7,1,  12,0,0, tzinfo=dt.timezone.utc)
window_weeks = 26 # +/-this many weeks around the Sunday on/after the pivot (so window_weeks x 2 + 1 events in total)
anti_flood_s = 1 # delay between API calls to avoid flooding Google's API

# ------------- skyfield astro functions --------------------------

def time_of_meridian_by_azim(date_dt):  # date_dt is a datetime
    # Andrew Hodgson method, iterating adjusting time until azimuth is due south
    eot_secs = 0 # start assuming eot = 0
    error_deg = 99 # ensure we go round the loop at least once
    iters = 0
    while abs(error_deg) >= 1/4800 : # 1/4800 : # 0.05s = 1/20 / (4 * 60) : get to within 0.05 sec
        iters += 1
        solar_noon_dt = date_dt + dt.timedelta(seconds = -eot_secs)
        sfdatetime = ts.utc(solar_noon_dt) # turn into a skyfield date
        sun_pos = greenwich.at(sfdatetime).observe(sun) # sun, seen from Greenwich on earth - astrometric
        _, dec, _ = sun_pos.radec() # get the sun's declination from the astrometric, not the apparent position
        app_sun_pos = sun_pos.apparent() # calcualte az/el including speed of light, refraction, gravity, apparently!
        (_, az, _) = app_sun_pos.altaz() # get azimuth (type: angle) - discard elev and distance
        error_deg = 180 - az.degrees # positive for sun still slow (sun not yet bearing 180)
        eot_secs -= error_deg *4*60 # next guess: increment offset - for sun slow, solar noon will be later than clock time 
        # end of iteration loop
    # "+3m 27s SF"
    eot_string = '+' if eot_secs>=0 else '-'
    eot_string += f"{int(abs(eot_secs)/60)}m {abs(eot_secs) % 60:.0f}s "
    eot_string += 'SF' if eot_secs>=0 else 'SS'
    print(f"By Azim:\t {solar_noon_dt.isoformat(sep=' ')}\t{eot_secs:10.3f}s\t{eot_string:10}\t{dec.degrees:10.3f}", file=open('output.tsv', 'a'))
    return (solar_noon_dt, eot_string, dec.degrees, dec.dstr())


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
    return (sun_at_meridian_dt, eot_string, 0)

# ------------- ical functions --------------------------------------

def make_ical_event(datetime, eot_string, dec_degrees, dec_string):
    event = Event()
    event.add('summary', f'{eot_string}')
    event.add('dtstart', datetime)   # defaults to UTC (e.g. 20220630T120344Z) 
    event.add('dtend', datetime)
    # &&ToDo add more fields to the ical event so it is the same as the gcal event (Description, not-busy, color)
    return event

# ------------- google calendar functions --------------------------

def create_gcal_event(service, timedate, summary, description):
    event = {
        'start' : {'dateTime': timedate, 'timeZone' : 'Europe/London'},
        'end' : {'dateTime': timedate, 'timeZone' : 'Europe/London'},
        'transparency' : 'transparent', # maps to not busy
        'colorId' : '5', # Banana
        'summary' : summary,
        'description' : description,
    }
    new_event = service.events().insert(calendarId=gmt_eot_weekly_calendar_id, body=event).execute()
    print(f"Gcal event created: {event}", file=open('output.tsv', 'a'))

# ------------- main function -------------------------------------

print(f"\nEquation of Time Calendar Generator")

# initialise skyfield
ts = load.timescale(builtin=True)
planets = load('de421.bsp')
earth, sun = planets['earth'], planets['sun']
esher = earth + Topos('51.3642523 N', '0.3583954 W')
greenwich = earth + Topos('51.477928 N', '0.0 W')

# initialise ical
ical = Calendar()

# initialise google calendar
gcal_service = google_calendar.calendar_login()

# calculate wanted window of wanted events window_start, window_end
# pull list of existing events in gmt eot calendar into current_list_dt
# delete any that are before or after the window
# calculate list of Sundays within the window
# identify any missing events and create them

print(f"EoT Calendar Generator", file=open('output.tsv', 'w'))  # starts a new file, overwrites the old

# force pivot to be a Sunday
offset_to_sunday = 6-pivot_dt.weekday() # 0=Mon, 6=Sun
pivot_dt = pivot_dt + dt.timedelta(days=offset_to_sunday) # forced to a Sunday
window_start_dt = pivot_dt + dt.timedelta(days = -window_weeks*7) # also a Sunday
window_end_dt = pivot_dt + dt.timedelta(days = window_weeks*7) # also a Sunday

window_end_zs = window_end_dt.isoformat()
window_start_zs = window_start_dt.isoformat()
print(f"window_start_zs \t{window_start_zs}", file=open('output.tsv', 'a'))
print(f"pivot_zs        \t{pivot_dt.isoformat()}", file=open('output.tsv', 'a'))
print(f"window_end_zs   \t{window_end_zs}", file=open('output.tsv', 'a'))

# get a list of existing google calendar events
existing_event_dates = [] # list of dates of already in-place entries in the window
if True:
    events_result = gcal_service.events().list(
            calendarId=gmt_eot_weekly_calendar_id, singleEvents=True, orderBy='startTime').execute()
    for event in events_result.get('items', []): # second parameter returns an empty array if nothing to get
        event_zs = event['start'].get('dateTime', event['start'].get('date')) # returns 'datetime' if exists, else 'date'
        if event_zs[:10] < window_start_zs[:10] or event_zs[:10] > window_end_zs[:10]: # ignore time and timezone
            action = 'Delete'
            print(f"Deleting event: {event_zs}, id: {event['id']}, {event['summary']}")
            gcal_service.events().delete(calendarId=gmt_eot_weekly_calendar_id, eventId=event['id']).execute()
            time.sleep(anti_flood_s) # avoid flooding Google's API
        else:
            action = 'Keep'
            existing_event_dates.append(event_zs[:10]) # just the date string, no time or timezone
        print(f"{action}\t Event: {event_zs}, id: {event['id']}, [{event['summary']}]", file=open('output.tsv', 'a'))

for i in range(0, (2 * window_weeks + 1) * 7, 7):  # step in weeks, starting on a Sunday
    date_dt = window_start_dt + dt.timedelta(days=i) # noon
    # Calculate EoT (two methods)
#    (meridian_dt, eot_string, dec_degrees, dec_string) = time_of_meridian_by_transit(date_dt)
    (azim_iter_dt, eot_string, dec_degrees, dec_string) = time_of_meridian_by_azim(date_dt)
    ical.add_component(make_ical_event(azim_iter_dt, eot_string, dec_degrees, dec_string))
    dec_string = dec_string.replace('deg', '°')
    #&&ToDo perhaps add location at Prime Meridian, Royal Observatory, Blackheath Ave, London SE10 8XJ, UK

    # If this date is not in existing_event_dates array, then call Google Calendar API to insert the event in calendar
    date_string = azim_iter_dt.isoformat()[:10] # just date part as string

    if date_string not in existing_event_dates :
        print(f"Creating event: {azim_iter_dt.isoformat(sep=' ')}, EoT: {eot_string}, dec: {dec_string}")
        create_gcal_event(gcal_service, azim_iter_dt.isoformat(), f"{eot_string}", 
            f"Sun is overhead the Prime Meridian\nSun's declination: {dec_degrees:10.4}° ({dec_string})")
        time.sleep(anti_flood_s) # avoid flooding the Google API
    else:
        # &&ToDo could maybe check that all parameters of the old event match the possible new event, and delete/recreate if not
        print(f"Keeping event: {date_string} (should be EoT: {eot_string} but not checked)")
    # end of per-week loop

f = open('AH EoT weekly.ics', 'wb')
f.write(ical.to_ical())
f.close()

print(f"\nFine.\n")

