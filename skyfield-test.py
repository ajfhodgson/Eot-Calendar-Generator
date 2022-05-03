from skyfield.api import Topos, load
import datetime as dt
import numpy as np
import math

(X, Y, Z) = (0, 1, 2) # constants for indexing of vector axes

# VALUES
# error values to be estimated
errors = np.array([
    0.0, # 0 mirror non-level roattion about x axis (+ve North down)
    0.0, # 1 mirror non-level roattion about y axis (+vs East down)
    0.0, # 2 error in laser x (actual = nominal + error)
    0.0, # 3 error in laser y (actual = nominal + error)
    0.0, # 4 error in laser z (actual = nominal + error)
    0.0, # 5 error in aperture z (actual = nominal + error)
    0.0  # 6 error in laser azimuth orientation (actual = nominal + error)
])

laser = np.array([1.0, 1.0, -1.80]) # wrt point on ceiling directly above aperture
aperture = np.array([0.0, 0.0, -1.80]) # wrt point on ceiling directly above aperture (z=0.0)

# CALIBRATION:
# calculate loss as sum of error distances of each reference point
# iterate adjusting the errors[] vector to minimise loss (across all reference points)
#
# N reference points: date-time, meas_az, meas_el
#   for each element in errors
#     calculate l-az, l-el (using current errors)
#     calcuate intercept(l-az, l-el) and intercept(meas_az, meas_el)
#     calculate distance between intercepts and sum them - this is loss for current errors
#       adjust error by delta - recalculate loss
#       if error is reduced, keep it, otherwise back it out
#
# to make this a gradient descent, we would calculate the loss improvement for a delta in each axis, 
# and apply the delta to each axis proportional to the improvement in that axis
# 

def sin_deg(ang_deg):
    return math.sin(math.radians(ang_deg))

def cos_deg(ang_deg):
    return math.cos(math.radians(ang_deg))

def intercept(origin, vector): # where vector from origin hits z=0
#    print(origin[X], vector[X], vector[Z], origin[Z])
#    print(origin[X], -vector[X]/vector[Z]*origin[Z])
    inter = np.array(
        [origin[X]-vector[X]/vector[Z]*origin[Z],
         origin[Y]-vector[Y]/vector[Z]*origin[Z],
         0])
    return inter

def az_el_a_to_b(a, b): # from point a towards point b
    d = b - a
    az = math.atan2(d[X], d[Y]) # radians at this point
    hyp = math.sqrt(d[X]*d[X] + d[Y]*d[Y])
    el = math.atan(d[Z]/hyp)
    return(math.degrees(az) % 360.0, math.degrees(el)) # return as degrees

def reflected(incident, e): # assumes almost horizontal mirror
    M = np.array( # Reflection transformation - for mirror with ex, ey, ez
        [[1.0-2.0*e[X]*e[X], -2.0*e[X]*e[Y], -2.0*e[X]*(1-e[Z])],
        [-2.0*e[X]*e[Y], 1.0-2.0*e[Y]*e[Y], -2.0*e[Y]*(1-e[Z])],
        [-2.0*e[X]*(1-e[Z]), -2.0*e[Y]*(1-e[X]), 1.0-2.0*(1-e[Z])*(1-e[Z])]])
    return M @ incident # vector of reflected ray (matrix product)

# test example data
Az = 170.0
El = 10.0
k1 = np.array( # vector of incident ray
    [sin_deg(Az-180) * cos_deg(-El), 
    cos_deg(Az-180) * cos_deg(-El),
    sin_deg(-El)] )
mirror_error = np.array([0.0, 0.0, 0.0])

print(k1)
print(reflected(k1, mirror_error))



print(f"\nTest of skyfield")
ts = load.timescale(builtin=True)
planets = load('de421.bsp')
earth, sun = planets['earth'], planets['sun']
esher = earth + Topos('51.3642523 N', '0.3583954 W')

ref_date_time = dt.datetime(2020,1,1,  12,0,0, tzinfo=dt.timezone.utc)


print(f"TimeDate\tS-Az\tS-El\tEOT\tx\ty\tL-Az\tL-El", file=open('output.tsv', 'w'))
for hr in range(-3, 4):
    for i in range(0, 366, 5):  
        delta = dt.timedelta(days=i, hours=hr)
        d2 = ref_date_time+delta
        sfdatetime = ts.utc(d2) # turn into a skyfield date
        sun_pos = esher.at(sfdatetime).observe(sun) # sun, seen from esher on earth
        app_sun_pos = sun_pos.apparent() # calcualte az/el including speed of light, refraction, gravity!
        (el, az, _) = app_sun_pos.altaz() # get az/el (type: angle) - discard distance
        sun_ray = np.array( # vector of incident ray
            # reciprocal of az, el since direction of ray is opposite to view of sun
            [sin_deg(az.degrees-180) * cos_deg(-el.degrees), 
            cos_deg(az.degrees-180) * cos_deg(-el.degrees),
            sin_deg(-el.degrees)] )
        spot = intercept(aperture, reflected(sun_ray, mirror_error))

        laser_act = laser + np.array([errors[2], errors[3], errors[4]])
        (l_az, l_el) = az_el_a_to_b(laser_act, spot)

        print(f"{d2.isoformat(sep=' ')}\t{az.degrees:.3f}\t{el.degrees:.3f}\t" + 
              f"{4*(180-az.degrees):7.3f}\t" + # 4* turns degrees into minutes of time
              f"{spot[X]:5.2f}\t{spot[Y]:5.2f}\t",
              f"{l_az:6.3f}\t{l_el:6.3f}\t",
            file=open('output.tsv', 'a'))

print(f"Fine.\n")


# Next - turn an az/el into an x-y on the ceiling
