# OpenRiverCam

## Installation
The Open River Cam software runs within a dockerized environment or can be deployed onto the cloud as separate services.

1. Install docker.  
More information: https://docs.docker.com/get-docker/.

2. Install docker-compose.  
More information: https://docs.docker.com/compose/install/.

3. Install Git.  
More information: https://git-scm.com/book/en/v2/Getting-Started-Installing-Git.

4. Clone repository.
Run
   ```
   git clone https://github.com/TAHMO/OpenRiverCam.git" in your terminal
   ```

5. Move to the target folder to run the software as a service
```
cd OpenRiverCam
```
## Usage
To run the software, simply:
1. Open a terminal 
2. Change directory to the location of the software, e.g.
```
cd /home/user/OpenRiverCam
```
3. Type the following to start the service
```
docker-compose up
```
Interaction with services:
* OpenRiverCam dashboard is available at http://localhost
* MinIO storage dashboard is available at http://localhost:9000
* RabbitMQ Management interface is available at http://localhost:15672
* Postgres database is exposed at port 5432 and can be connected to with pgAdmin or any other PostgreSQL client.

Please note: it's strongly advised to change the default credentials in the ".env" file, especially when opening the ports for other machines.

## Examples
Example task for queue:
```json
{
  "type": "extract_snapshots",
  "kwargs": {
    "movie": {
      "file": {
        "bucket": "test-bucket",
        "identifier": "schedule_20201120_142304.mkv"
      }
    },
    "camera": {
      "name": "Foscam E9900P",
      "configuration": {},
      "lensParameters": {
        "k": 0.5
      }
    }
  }
}
```

Command to enter processing container shell:
```
docker exec -it openrivercam_processing_1 bash
```

## Dictionaries used within processing queue
All communication about objects is arranged in serializable dictionaries. Below, we keep track of what dictionaries may exist.
These dictionaries are communicated as json strings 

### camera_type 
defines ```camera_type```, and can be reused if you for instance have the same ```camera_type``` at multiple locations
```json
{
    "name": "Foscam E9900P",  # user-chosen name for camera
    "lensParameters": {  # the lens parameters need to be known or calibrated
        "k1": -10.0e-6,
        "c": 2,
        "f": 8.0,
    }
}
```

### camera
defines one specific camera with id, and its connection details, no details about exact position.
```json
{
   "id": 1,  # int
   "camera_type": camera_type,
   "site": site,
   "status": 1,  # int defining state
   "connection": {
      "type": "ftp",
      "url": "data.tahmo.org",
      "port": 21,
      "username": "rick",
      "hashed_password": "hashed_passwd",
    }
}
```

### Site
Contains general information about a river gauging ```site```
```json
{
    "name": "Hommerich",  # str, name of user
    "id": 1,  # some uuid for relational database purposes
    "position": (345003, 1298345, 105),  # approximate geographical location of site in crs (x, y, z) coordinates in metres.
    "crs": 28992,  # int, coordinate ref system as EPSG code
}
```

### bbox
Component of the ```aoi``` dictionary within ```camera_config```. Contains a geojson with a rotated rectangle, needed for ```aoi```.
```json
{
    "crs": {
        "properties": {
            "code": 32737
        }, "type": "EPSG"
    }, "features": [{"geometry": {"coordinates": [[[-6.171107, 9.763121], [9.018206, 11.710014], [10.082358, 3.407686], [-5.106955, 1.460793], [-6.171107, 9.763121]]], "type": "Polygon"}, "properties": {"ID": 0}, "type": "Feature"}], "type": "FeatureCollection"
}

```

### gcps
```gcps``` are a component of ```camera_config```. Contains the control points, their pixel coordinates, the real world coordinates, the zero-water level reference levelm and the water level measured during the gcp field work.
```json
{
    "src": [(992, 366), (1545, 403), (1773, 773), (943, 724)],
    "dst": [(0.25, 6.7), (4.25, 6.8), (4.5, 3.5), (0.0, 3.5)],
    "z_0": 100.0,  # reference height of zero water level compared to the crs used (z is crs related, h is staff gauge related)
    "h_ref": 2.0,  # actual water level during taking of the gcp points, as measured on the staff gauge
}
```

### corners
Pixel ```corner``` coordinates are specified explicitly using upstream left, downstream left, downstream right, upstream right corners of aoi in pixel coordinates.
Explicit naming (rather than a simple list of coordinates) is used to ensure there is no question about the order that should be used.
```json
{
    "up_left": (200, 100),
    "down_left": (1850, 150),
    "down_right": (1890, 900),
    "up_right": (50, 970),
}
```

### camera_config
The ```camera_config``` holds many of the above dictionaries, and contains all information to understand where in geographical space a movie shot is.
Therefore it requires the camera (lens parameters), the site (attribution to correct location), ```gcps```, pixel ```corners```, and (derived from pixel ```corners```)
the ```aoi``` object's ```bbox```, which also contains the amount of ```rows``` and ```cols``` within the AOI. In addition it also requires a ```resolution``` in meters defining interrogation windows used in the PIV analysis, 
and the position of the camera, which can be used toi interpret where in space the gcps are with the current water level.

```json
{
    "camera": camera,  # dict, camera object, relational, because a camera configuration belongs to a certain camera.
site.
    "movie_settings": {
        "resolution": "1920x1080",
        "fps": 25
    }
    "time_start": "2020-12-16T00:00:00",  # start time of valid range
    "time_end": "2020-12-31T00:00:00",  # end time of valid range, can for instance be used to find the right camera config with a given movie
    "gcps": gcps,    # dict, gcps dictionary, see above
    "corners": corners,  # dict containining corner pixel coordinates, see above
    "aoi": {
        "bbox": bbox,  # dict in geojson format, with crs projection, order of corner points is up-left, down-left, down-right, up-right, -up-left
        "rows": 10,  # int, amount of rows (from left bank to right bank) for interrogation window
        "cols": 30,  # int, amount of cols (from upstream to downstream) for interrogation window
    },
    "resolution": 0.01,  # resolution to be used in reprojection to AOI
    "lensPosition": [-3.0, 8.0, 110.0],  # we could also make this a geojson but it is just one point (x, y, z)
}

```

### movie
A ```movie``` object is associated with a ```camera_config``` and only contains file information.
```json
{
    "type": "configuration",  # str, defines what the movie is used for, either "configuration" or "normal"
    "camera_config": camera_config,  # dict, camera_config object, relational, because a movie belongs to a given camera_config (which in turn belongs to a site).
    "file": {  # file contains the actual filename, and the bucket in which it sits.
        "bucket": "example",
        "identifier": "example_video.mp4"
    },
    "timestamp": "2021-01-01T00:05:30Z",
    "resolution": "1920x1080",
    "fps": 25.,  # float
    "bathymetry": bathymetry,
    "actual_water_level": 3.4  # float, water level with reference to gauge plate zero level
}
```

### frame
```frame``` holds a lens corrected frame in RGB (i.e. NOT projected). This is used only for the user to aid with the camera_config
setup, i.e. to point out gcps in the raw imagery, and to define corner coordates o the aoi

```json
{
    "movie": movie,  # a frame belongs to a certain movie, so needs a relation
    "file": {  # file contains the actual filename, and the bucket in which it sits.
        "bucket": "example",
        "identifier": "frame_0003_000040.jpg"  # file name convention is "frame_<frame_no in 4dec.>_<frametime in ms, 6dec>.jpg
    }
}

```

### proj_frame
```proj_frame``` holds a projected frame in local crs, geotiff format. The crs and coordinates are inside the geotiff
```json
{
    "movie": movie,  # a projected frame belong to a certain movie, so needs a relation
    "file": {  # file contains the actual filename, and the bucket in which it sits.
        "bucket": "example",
        "identifier": "proj_0003_000040.tif"  # file name convention is "proj_<frame_no in 4dec.>_<frametime in ms, 6dec>.tif
    }
}
```

### bathymetry
```bathymetry``` contains a list of coordinates inc. z-coordinate of bathymetry measured in crs.
```json
{
    "crs": 28992,  # int, epsg code in [m], only projected coordinate systems are supported
    "coords": [[1., 2., 3], [2, 2, 4], [...],   ... ]  # list of (x, y, z) tuples defined in crs [m], coords are not valid in the example
}

```
### v (velocity)
```v``` object contains raw velocities as (t, y, x) time series so that it can be displayed in any NetCDF-CF compatible viewer. 
Several keyword arguments can be passed that are specifically used to process the frames into velocities.
This includes window_size (interrogation window in pixels), overlap (overlap in pixels between windows), and search_area_size (size of area that is searched for correlations in PIV).
```json
{
    "movie": movie,  # a set of velocities belongs to a certain movie, so needs a relation
    "file": {  # file contains the actual filename, and the bucket in which it sits.
        "bucket": "example",
        "identifier": "v.nc"  # netcdf file containing all info for velocity, inc naming conventions, so that it can be
    }
    "piv_kwargs": {
        "window_size": 60,
        "overlap": 30,
        "search_area_size": 60,
    },

}

```
### v_filter
```v_filter``` object contains filtered and filled in velocities as (t, y, x) time series so that it can be displayed in any NetCDF-CF compatible viewer
```json
{
    "movie": movie,  # a projected frame belong to a certain movie, so needs a relation
    "file": {  # file contains the actual filename, and the bucket in which it sits.
        "bucket": "example",
        "identifier": "v_filter.nc"  # netcdf file containing all info for velocity, inc naming conventions, so that it can be
    }
}
```

### q_filter
```q_filter``` contains filtered and filled in velocities over cross-section as (t, points) time series where points contain the x, y coordinates.
of each cross-sectional point. NetCDF-CF compatible.
```json
{
    "movie": movie,  # a projected frame belong to a certain movie, so needs a relation
    "file": {  # file contains the actual filename, and the bucket in which it sits.
        "bucket": "example",
        "identifier": "q_filter.nc"
        # netcdf file containing all info for cross-sectional velocities, inc naming conventions
    }
}
```

### flow_filter
```flow_filter``` contains cross-section integrated flow in m3/s (t) time series. NetCDF-CF compatible.
```json
{
    "movie": movie,  # a projected frame belong to a certain movie, so needs a relation
    "file": {  # file contains the actual filename, and the bucket in which it sits.
        "bucket": "example",
        "identifier": "flow_filter.nc"
        # netcdf file containing all info for integrated river flow, inc naming conventions
    }
}
```
From ```flow_filter``` a number of statistics are derived for storage in the database.

## Database Migrations
After making changes to field. Generate migration ```alembic revision --autogenerate -m "migration definition"```

Migrate the database ``` alembic upgrade head ```