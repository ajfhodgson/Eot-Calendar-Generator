from skyfield.api import Topos, load
import datetime as dt
import time
import google_calendar

# This program maintains a Google Calendar containing a series of events, within a user-specified span, at daily or
# weekly intervals, showing the EoT for each day of interest. 
#
# The time of the event is the minute when the sun is overhead the Greenwich meridian (i.e. solar noon at the prime meridian, 12:00 + EoT)
# First it retrieves all existing events in the calendar, to be able to see which ones need adding, changing or deleting.
# Then for each date in the span of interest, it calculates the EoT (by several methods for comparison), 
# and looks the date up in the list of existing events, leaving any that match exactly (includng summary and description), 
# deleting and reinserting any that are different, and inserting any that are absent.
# Finally it deletes any resundant existing events that were not kept or changed (e.g. when running for a new quarter, removes old events)
#
# to execute a 'from scratch' run, execute with a one-day span (will delete all others), before executing with the desired span.


# three candidate calendars
weekly_gmt_eot_calendar_id = "prgqbrj080r4nb1091nsusl978@group.calendar.google.com"
daily_gmt_eot_calendar_id =  "d81o7gedfsmjakj5qbgp0kobec@group.calendar.google.com"
test_gmt_eot_calendar_id =   "e8fprgrdgm6nbghkihnui26avc@group.calendar.google.com"
anti_flood_s = 1 # delay between API calls to avoid flooding Google's API

# parameters for this run:

google_calendar_id = weekly_gmt_eot_calendar_id # which calendar to write to
window_start_dt = dt.datetime(2022,7,3,  12,0,0, tzinfo=dt.timezone.utc) # should be a Sunday for a weekly run
window_end_dt   = dt.datetime(2023,6,30, 12,0,0, tzinfo=dt.timezone.utc) # inclusive!
interval_days = 7 # 1 for daily, 7 for weekly
test_run = False # whether to actually write to the Google Calendar or just show the proposals
pretend = '(Pretend)' if test_run else ''

if interval_days == 7 and window_start_dt.weekday() != 6 :
    print("SURELY YOU WANT WEEKLY EVENTS ON SUNDAYS, NO?")
    quit()

# ------------- main function -------------------------------------

def main():
    global window_start_dt, window_end_dt, ts, sun, north_pole, greenwich, equator

    print(f"\nEquation of Time Calendar Generator")

    # initialise skyfield
    ts = load.timescale(builtin=True)
    planets = load('de421.bsp')
    earth, sun = planets['earth'], planets['sun']
    north_pole = earth + Topos('90.0 N', '0.0 W')
    greenwich = earth + Topos('51.477928 N', '0.0 W')
    equator = earth + Topos('0.0 N', '0.0 W')

    gcal_service = google_calendar.calendar_login() # initialise google calendar

    kept = changed = added = deleted = 0
    print(f"EoT Calendar Generator", file=open('output.tsv', 'w'))  # starts a new file, overwrites the old

    window_start_zs = window_start_dt.isoformat()
    window_end_zs = window_end_dt.isoformat()
    print(f"window_start_zs \t{window_start_zs}", file=open('output.tsv', 'a'))
    print(f"window_end_zs   \t{window_end_zs}", file=open('output.tsv', 'a'))

    # get a list of existing google calendar events
    existing_event_dates = {} # list of dates of already in-place entries in the window
    events_result = gcal_service.events().list(
            calendarId=google_calendar_id, singleEvents=True, orderBy='startTime', maxResults=500).execute()
    for event in events_result.get('items', []): # second parameter returns an empty array if nothing to get
        event_zs = event['start'].get('dateTime', event['start'].get('date')) # returns 'datetime' if exists, else 'date'
        digest = {"id": event['id'], "summ": event['summary'], "desc": event['description']}
        if event_zs[:10] in existing_event_dates:
            # WOW! two events in one day - that's not right! Delete this second one immediately!
            print(f"{pretend} Deleting Duplicated event: {event_zs[:10]}, id: {digest['id']}, {digest['summ']}")
            deleted += 1
            if not test_run : # delete old, create new
                gcal_service.events().delete(calendarId=google_calendar_id, eventId=digest['id']).execute()
        else:
            existing_event_dates[event_zs[:10]] = digest # remember the salient details for comparison later

    span = window_end_dt - window_start_dt # results in a delta time
    days = span.days
    for i in range(0, days + 1, interval_days): # for each date of interest
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
        print("\t\t" + deb_str)

        # three possibilities:
        # - no event exists for this date - add this new one
        # - an event exists, but summary or description is different - delete it and add new
        # - an event exists, and summary and description match - keep it

        iso_date_time_string = azim_iter_dt.isoformat() # for google calendar API must be strinct ISO format
        date_time_string = azim_iter_dt.isoformat(sep=' ') # more legible format for printing
        date_string = date_time_string[:10] # just date part
        summ = eot_string
        desc = f"Sun is overhead the Prime Meridian\nSun's declination: {dec_degrees:10.4}° ({dec_string})"

        # If this date is not in the existing_event_dates array, then call Google Calendar API to insert the event in calendar
        if date_string not in existing_event_dates :
            print(f"{pretend} Creating event: {date_time_string}, EoT: {eot_string}, dec: {dec_string}")
            added += 1
            if not test_run:
                create_gcal_event(gcal_service, iso_date_time_string, summ, desc)
                time.sleep(anti_flood_s) # avoid flooding the Google API
        else:
            existing = existing_event_dates[date_string]
            if existing["summ"] == summ and existing["desc"] == desc : # all good!
                print(f"Keeping event: {date_time_string}, EoT: {eot_string}, dec: {dec_string}")
                kept += 1
                del existing_event_dates[date_string] # remove from the list to be deleted at the end
            else : # exists, but it needs changing
                print(f"{pretend} Changing event: {date_time_string}, id: {existing['id']}, {existing['summ']} -> {summ}")
                changed += 1
                del existing_event_dates[date_string] # remove from the list to be deleted at the end
                if not test_run : # delete old, create new
                    gcal_service.events().delete(calendarId=google_calendar_id, eventId=existing['id']).execute()
                    time.sleep(anti_flood_s) # avoid flooding Google's API
                    create_gcal_event(gcal_service, iso_date_time_string, summ, desc)
                    time.sleep(anti_flood_s) # avoid flooding the Google API
    # end of calculate/create loop

    # finally, delete all the redundant existing events
    for date_string in existing_event_dates : # any that haven't been kept or changed
        existing = existing_event_dates[date_string]
        print(f"{pretend} Deleting event: {date_string}, id: {existing['id']}, {existing['summ']}")
        deleted += 1
        if not test_run : # delete old, create new
            gcal_service.events().delete(calendarId=google_calendar_id, eventId=existing['id']).execute()

    print(f"Events added: {added}, changed: {changed}, kept: {kept}, deleted: {deleted}")
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
