from skyfield.api import Topos, load
import datetime as dt
import time
from icalendar import Calendar, Event
import google_calendar

# This program builds a Google Calendar containing a series of dates, N weeks either side of a 'pivot date' at daily or
# weekly intervals, showing the EoT for each day of interest. 
# The time of the event is the minute when the sun is overhead Greenwich meridian (i.e. solar noon at the prime meridian)
# rather than calculating the EoT for 12:00 GMT on that day.
# First it retrieves all existing events in the calendar, and deletes any that fall outside the desired period.
# Then it inserts in the calendar any events that are missing.
# NOTE - the existing events that are inside the period may not match the new ones calculated!

weekly_gmt_eot_calendar_id = "prgqbrj080r4nb1091nsusl978@group.calendar.google.com"
daily_gmt_eot_calendar_id =  "d81o7gedfsmjakj5qbgp0kobec@group.calendar.google.com"
test_gmt_eot_calendar_id =   "e8fprgrdgm6nbghkihnui26avc@group.calendar.google.com"

# parameters for this run:
pivot_dt = dt.datetime(2023,7,1,  12,0,0, tzinfo=dt.timezone.utc)
window_weeks = 27 # +/-this many weeks around the Sunday on/after the pivot (so window_weeks x 2 + 1 events in total)
google_calendar_id = daily_gmt_eot_calendar_id
interval_days = 1 # 1 for daily, 7 for weekly
anti_flood_s = 1 # delay between API calls to avoid flooding Google's API
test_run = True # whether to actually write to the Google Calendar or just show the proposals
from_scratch = True # if True, delete ALL old events, and add ALL new events, otherwise, delete out of range, add any missing

# ------------- main function -------------------------------------

def main():
    global pivot_dt, ts, sun, north_pole, greenwich, equator

    print(f"\nEquation of Time Calendar Generator")

    # initialise skyfield
    ts = load.timescale(builtin=True)
    planets = load('de421.bsp')
    earth, sun = planets['earth'], planets['sun']
    north_pole = earth + Topos('90.0 N', '0.0 W')
    greenwich = earth + Topos('51.477928 N', '0.0 W')
    equator = earth + Topos('0.0 N', '0.0 W')

    gcal_service = google_calendar.calendar_login() # initialise google calendar

    print(f"EoT Calendar Generator", file=open('output.tsv', 'w'))  # starts a new file, overwrites the old

    # force pivot day to be a Sunday
    offset_to_sunday = 6 - pivot_dt.weekday() # 0=Mon, 6=Sun
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

    events_result = gcal_service.events().list(
            calendarId=google_calendar_id, singleEvents=True, orderBy='startTime').execute()

    for event in events_result.get('items', []): # second parameter returns an empty array if nothing to get
        event_zs = event['start'].get('dateTime', event['start'].get('date')) # returns 'datetime' if exists, else 'date'
        if from_scratch or event_zs[:10] < window_start_zs[:10] or event_zs[:10] > window_end_zs[:10]: # ignore time and timezone
            action = 'Delete'
            print(f"Deleting event: {'(not really) ' if test_run else ''} {event_zs}, id: {event['id']}, {event['summary']}")
            if not test_run:
                gcal_service.events().delete(calendarId=google_calendar_id, eventId=event['id']).execute()
                time.sleep(anti_flood_s) # avoid flooding Google's API
        else:
            action = 'Keep'
            existing_event_dates.append(event_zs[:10]) # just the date string, no time or timezone
        print(f"{action}\t Event: {event_zs}, id: {event['id']}, [{event['summary']}]", file=open('output.tsv', 'a'))

    for i in range(0, (2 * window_weeks + 1) * 7, interval_days):  # step in weeks, starting on a Sunday
        date_dt = window_start_dt + dt.timedelta(days=i) # noon
        # Calculate EoT (several methods)
        (transit_dt, eot_string, dec_degrees, dec_string) = time_of_meridian_by_transit(date_dt) # rhodesmill method
        (azim_noon_dt, eot_string, dec_degrees, dec_string) = time_of_meridian_by_ha_at_12h(date_dt) # add noon azimuth method
        (azim_iter_dt, eot_string, dec_degrees, dec_string) = time_of_meridian_by_azim(date_dt) # AH method
        dec_string = dec_string.replace('deg', '°')

        transit_eot_s = transit_dt.second + transit_dt.microsecond/1000000
        noon_eot_s = azim_noon_dt.second + azim_noon_dt.microsecond/1000000
        azim_eot_s = azim_iter_dt.second + azim_iter_dt.microsecond/1000000

        deb_str = f"Transit method: {transit_eot_s:10.5f}, "
        deb_str += f"Azimuth method: {azim_eot_s:10.5f} ({(transit_eot_s-azim_eot_s):10.5f}s), "
        deb_str += f"HourAng method: {noon_eot_s:10.5f} ({(transit_eot_s-noon_eot_s):10.5f}s). "
        print(deb_str)

        # If this date is not in the existing_event_dates array, then call Google Calendar API to insert the event in calendar
        date_string = azim_iter_dt.isoformat()[:10] # just date part as string
        if date_string not in existing_event_dates :
            print(f"Creating event: {'(not really) ' if test_run else ''} {azim_iter_dt.isoformat(sep=' ')}, EoT: {eot_string}, dec: {dec_string}")
            if not test_run:
                create_gcal_event(gcal_service, azim_iter_dt.isoformat(), f"{eot_string}", 
                    f"Sun is overhead the Prime Meridian\nSun's declination: {dec_degrees:10.4}° ({dec_string})")
                time.sleep(anti_flood_s) # avoid flooding the Google API
        else:
            # &&ToDo could maybe check that all parameters of the old event match the possible new event, and delete/recreate if not
            print(f"Keeping event: {date_string} (should be EoT: {eot_string} but not checked)")
        # end of per-week loop

print(f"\nFine.\n")


# ------------- skyfield astro functions --------------------------

def time_of_meridian_by_azim(date_dt):  # date_dt is a datetime
    # Andrew Hodgson method, iterating adjustment of the time until sun's azimuth is due south
    # strictly speaking, this is not EoT at noon, but EoT as the sun passes the meridian
    eot_at_noon_secs = eot_at_noon(date_dt) # reference, the conventional approach
    eot_secs = eot_at_noon_secs # use this as a very gross starting point
    error_deg = 99 # ensure we go round the loop at least once
    iters = 0
    while abs(error_deg) >= 1/48000 : # 1/48000 : # 0.005s = 1/20 / (4 * 60) : get to within 0.005 sec
        iters += 1
        solar_noon_dt = date_dt + dt.timedelta(seconds = -eot_secs)
        sfdatetime = ts.utc(solar_noon_dt) # turn into a skyfield date
        sun_pos = greenwich.at(sfdatetime).observe(sun) # sun, seen from Greenwich on earth - astrometric
        (ra, dec, _) = sun_pos.radec() # get the sun's declination from the astrometric, not the apparent position
        app_sun_pos = sun_pos.apparent() # calcualte az/el including speed of light, refraction, gravity, apparently!
        (_, az, _) = app_sun_pos.altaz() # get azimuth (type: angle) - discard elev and distance
        error_deg = 180 - az.degrees # positive for sun still slow (sun not yet bearing 180)
        eot_secs += -error_deg *4*60 # next guess: increment offset - for sun slow, solar noon will be later than clock time 
        # end of iteration loop
    # "+3m 27s SF"
    eot_string = '+' if eot_secs>=0 else '-'
    int_eot_secs = round(eot_secs)
    eot_string += f"{int(abs(int_eot_secs)/60)}m {abs(int_eot_secs) % 60:.0f}s "
    eot_string += 'SF' if eot_secs>=0 else 'SS'
    tsv_string = f"By Azim:\t {solar_noon_dt.isoformat(sep=' ')}\t{eot_secs:10.3f}s\t{eot_string:10}\t{dec.degrees:10.3f}\t"
    tsv_string += f"{iters}\t{eot_at_noon_secs:10.3f}s\t{(eot_secs-eot_at_noon_secs):10.3f}s"
    print(tsv_string, file=open('output.tsv', 'a'))
    return (solar_noon_dt, eot_string, dec.degrees, dec.dstr())

def time_of_meridian_by_ha_at_12h(date_dt):  # date_dt is a datetime
    # Non-iteration method - find eot at noon from hour angle from Greenwich at noon, then simply add this to noon
    # to give time of sun passing meridian
    sfdatetime = ts.utc(date_dt) # turn into a skyfield date

    np_sun_pos = north_pole.at(sfdatetime).observe(sun) # sun, seen from North Pole on earth - astrometric
    (_, np_dec, _) = np_sun_pos.radec() # get the sun's declination from the astrometric, not the apparent position
    (np_hour_angle, np_dec, dist) = np_sun_pos.hadec() # hour angle
    np_error_deg = np_hour_angle._degrees # positive for sun slow (sun not yet bearing 180)
    np_eot_secs = np_error_deg * 4*60

    gr_sun_pos = greenwich.at(sfdatetime).observe(sun) # sun, seen from North Pole on earth - astrometric
    (_, gr_dec, _) = gr_sun_pos.radec() # get the sun's declination from the astrometric, not the apparent position
    (gr_hour_angle, other_gr_dec, dist) = gr_sun_pos.hadec() # hour angle
    gr_error_deg = gr_hour_angle._degrees # positive for sun slow (sun not yet bearing 180)
    gr_eot_secs = gr_error_deg * 4*60

    eq_sun_pos = equator.at(sfdatetime).observe(sun) # sun, seen from North Pole on earth - astrometric
    (_, eq_dec, _) = eq_sun_pos.radec() # get the sun's declination from the astrometric, not the apparent position
    (eq_hour_angle, eq_dec, dist) = eq_sun_pos.hadec() # hour angle
    eq_eot_secs = eq_hour_angle._degrees * 4*60  # positive for sun slow (sun not yet bearing 180)

    eot_secs = np_eot_secs
    solar_noon_dt = date_dt + dt.timedelta(seconds = -eot_secs)
    eot_string = '+' if eot_secs>=0 else '-'
    eot_string += f"{int(abs(eot_secs)/60)}m {abs(eot_secs) % 60:.0f}s "
    eot_string += 'SF' if eot_secs>=0 else 'SS'
    tsv_string = f"At 00h: \t {solar_noon_dt.isoformat(sep=' ')}\t{eot_secs:10.3f}s\t{eot_string:10}\t{np_dec.degrees:10.3f}\t"
    print(tsv_string, file=open('output.tsv', 'a'))
    return (solar_noon_dt, eot_string, gr_dec.degrees, gr_dec.dstr())

def time_of_meridian_by_az_from_pole_at_noon(date_dt):  # date_dt is a datetime
    # Non-iteration method - find eot at noon from azimuth from North Pole, then simply add this to noon
    sfdatetime = ts.utc(date_dt) # turn into a skyfield date
    sun_pos = north_pole.at(sfdatetime).observe(sun) # sun, seen from North Pole on earth - astrometric
    (_, dec, _) = sun_pos.radec() # get the sun's declination from the astrometric, not the apparent position
    app_sun_pos = sun_pos.apparent() # calcualte az/el including speed of light, refraction, gravity, apparently!
    (_, az, _) = app_sun_pos.altaz() # get azimuth (type: angle) - discard elev and distance
    error_deg = 180 - az.degrees # positive for sun slow (sun not yet bearing 180)
    eot_secs = -error_deg * 4*60
    solar_noon_dt = date_dt + dt.timedelta(seconds = -eot_secs)
    eot_string = '+' if eot_secs>=0 else '-'
    eot_string += f"{int(abs(eot_secs)/60)}m {abs(eot_secs) % 60:.0f}s "
    eot_string += 'SF' if eot_secs>=0 else 'SS'
    tsv_string = f"At Noon:\t {solar_noon_dt.isoformat(sep=' ')}\t{eot_secs:10.3f}s\t{eot_string:10}\t{dec.degrees:10.3f}\t"
    print(tsv_string, file=open('output.tsv', 'a'))
    return (solar_noon_dt, eot_string, dec.degrees, dec.dstr())

def eot_at_noon(date_dt):  # date_dt is a datetime - assumed to be noon
    eot_secs = 0 # start assuming eot = 0
    sfdatetime = ts.utc(date_dt) # turn into a skyfield date
    sun_pos = north_pole.at(sfdatetime).observe(sun) # sun, seen from North Pole on earth - astrometric
    app_sun_pos = sun_pos.apparent() # calcualte az/el including speed of light, refraction, gravity, apparently!
    (_, az, _) = app_sun_pos.altaz() # get azimuth (type: angle) - discard elev and distance
    error_deg = 180 - az.degrees # positive for sun slow (sun not yet bearing 180)
    eot_secs = -error_deg * 4*60
    return (eot_secs)


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
    sun_at_transit_dt = times[0].utc_datetime() # convert from skyfield Time to datetime
    eot_secs = (date_dt - sun_at_transit_dt).total_seconds() # sun fast => positive sign
    eot_string = "+" if eot_secs>=0 else '-'
    eot_string += f"{int(abs(eot_secs)/60)}m {abs(eot_secs) % 60:.0f}s "
    eot_string += 'SF' if eot_secs>=0 else 'SS'

    print(f"By Transit:\t {sun_at_transit_dt.isoformat(sep=' ')}\t{eot_secs:10.3f}s\t{eot_string:10}", file=open('output.tsv', 'a'))
    return (sun_at_transit_dt, eot_string, 0, "")

# ------------- google calendar functions --------------------------

def create_gcal_event(service, timedate, summary, description):
    event = {
        'start' : {'dateTime': timedate, 'timeZone' : 'Europe/London'},
        'end' : {'dateTime': timedate, 'timeZone' : 'Europe/London'},
        'transparency' : 'transparent', # maps to not busy
        'colorId' : '5', # Banana
        'summary' : summary,
#        'location' : 'Prime Meridian, Greenwich, UK', # Don't do this, it just adds repetitive clutter to the calendar
        'description' : description,
    }
    new_event = service.events().insert(calendarId=google_calendar_id, body=event).execute()
    print(f"Gcal event created: {event}", file=open('output.tsv', 'a'))

# ------------- main function -------------------------------------
if __name__ == "__main__":
    main()
