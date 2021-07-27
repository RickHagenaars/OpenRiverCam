from flask import Blueprint, jsonify, request, flash, url_for, redirect
from models.bathymetry import Bathymetry, BathymetryCoordinate
from models import db
from jsonschema import validate, ValidationError
from io import StringIO
import csv
import pyproj

def geojson_linestring(lon_lat, props):
    """

    :param lon_lat: list of (x, y) tuples
    :param props: dictionary of properties belonging to LineString feature
    equal in length as amount of features
    :return:
    """
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": lon_lat},
                "properties": props,
            }
        ],
    }

def read_epsg(f):
    """
    Read EPSG code from first line of the file.

    :param f: File handle.
    :return: string or void
    """
    line = f.readline()
    if "EPSG:" in line.upper():
        try:
            # string string from any returns
            line = line.strip("\n")
            epsg_code = pyproj.crs.CRS(line)
            return epsg_code
        except:
            flash('Header does not contain a proper EPSG-code (such as "EPSG:4326")')
    else:
        flash('No EPSG code in header')


def read_coords(f):
    """
    Read coordinate lines from file and return a dict with a list of coordinates.

    :rtype: object
    """
    reader = csv.DictReader(f, fieldnames=['x', 'y', 'z'], delimiter=',')
    # skip the header line
    # next(reader)
    result = {"coordinates": []}
    print("another thing here")
    for n, row in enumerate(reader):
        if len(row) != 3:
            flash(f"Line {n + 1} contains {len(row)} comma-separated numbers instead of 3.")
            raise ValidationError(f"Incorrect row detected on line {n + 1}")
        if None in list(row.values()):
            flash(f"At least one value of 3 comma-separated values is missing")
            raise ValidationError(f"At least one value of 3 comma-separated values is missing")
        result["coordinates"].append(row)
    if len(result["coordinates"]) < 6:
        flash(f"Coordinates Must be a minimum of 6", "error")
        raise ValidationError(f"Coordinates Must be a minimum of 6")
    return result


bathymetry_api = Blueprint("bathymetry_api", __name__)
schema = {
    "type": "object",
    "properties": {
        "coordinates": {
            "type": "array",
            "items": {
                "x": {"type": "number"},
                "y": {"type": "number"},
                "z": {"type": "number"}
            }
        }
    }
}

@bathymetry_api.route("/api/bathymetry/<id>", methods=["POST"])
def bathymetry_coordinates(id):
    """
    API endpoint to overwrite X,Y,Z coordinates for a specific bathymetry.

    :param id: bathymetry identifier
    :return:
    """
    content = request.get_json(silent=True)
    print(f"Content = {content}")
    validate(instance=content, schema=schema)
    bathymetry = Bathymetry.query.get(id)
    if not bathymetry:
        raise ValueError("Invalid bathymetry with identifier %s" % id)

    BathymetryCoordinate.query.filter(BathymetryCoordinate.bathymetry_id == bathymetry.id).delete()
    for coordinate in content["coordinates"]:
        db.add(BathymetryCoordinate(x=coordinate['x'],y=coordinate['y'],z=coordinate['z'],bathymetry_id=bathymetry.id));

    db.commit()
    return jsonify(bathymetry.to_dict())

@bathymetry_api.route("/api/bathymetry_txt/<id>", methods=["GET", "POST"])
def bathymetry_coordinates_txt(id):
    """
    API endpoint to transform and store the posted X,Y,Z coordinates text blob in the specified bathymetry.

    :param id: bathymetry identifier
    :rtype: object
    """
    content = request.get_json(silent=True)
    print(content)
    # parse content
    f = StringIO(content.replace(' ', ''))
    result = read_coords(f)
    validate(instance=result, schema=schema)
    bathymetry = Bathymetry.query.get(id)
    if not bathymetry:
        raise ValueError("Invalid bathymetry with identifier %s" % id)
    BathymetryCoordinate.query.filter(BathymetryCoordinate.bathymetry_id == bathymetry.id).delete()
    for coordinate in result["coordinates"]:
        db.add(BathymetryCoordinate(x=coordinate["x"],y=coordinate["y"],z=coordinate["z"], bathymetry_id=bathymetry.id))

    db.commit()
    return jsonify(bathymetry.to_dict())

@bathymetry_api.route("/api/bathymetry_details/<id>", methods=["GET"])
def bathymetry_details(id):
    """
    API endpoint to retrieve bathymetry information including the bathymetry coordinates in a geojson.

    :param id: bathymetry identifier
    :return: JSON object with site and bathymetry information
    """
    bathymetry = Bathymetry.query.get(id)
    coordinates = BathymetryCoordinate.query.filter(BathymetryCoordinate.bathymetry_id == bathymetry.id).all()
    # provide coordinates in the site's crs
    crs_bathymetry = pyproj.CRS.from_epsg(bathymetry.crs if bathymetry.crs is not None else 4326)  # assume WGS84 latlon if not provided
    crs_site = pyproj.CRS.from_epsg(bathymetry.site.position_crs)
    transform = pyproj.Transformer.from_crs(crs_bathymetry, crs_site, always_xy=True)
    coordinates_site_crs = [list(transform.transform(c.x, c.y)) + [c.z] for c in coordinates]

    # left-bank to right-bank distances from point to point, for plotting in Highchart
    pos_0 = coordinates_site_crs[0]
    bathym_yz = [[round(((c[0]-pos_0[0])**2+(c[1]-pos_0[1])**2)**0.5, 2), round(c[2], 2)] for c in coordinates_site_crs]

    # project x, y to EPSG:4326 (WGS84 lat lon) and make into geojson for plotting in leaflet
    bathym_positions = [(c.x, c.y) for c in coordinates]
    crs_bathymetry = pyproj.CRS.from_epsg(bathymetry.crs if bathymetry.crs is not None else 4326)
    crs_latlon = pyproj.CRS.from_epsg(4326)
    transform = pyproj.Transformer.from_crs(crs_bathymetry, crs_latlon, always_xy=True)
    bathym_positions_latlon = [transform.transform(*c) for c in bathym_positions]

    # retrieve site in lat-long position, for plotting in leaflet
    site_position = [bathymetry.site.position_y, bathymetry.site.position_x]

    data = dict(
        site_position=site_position,
        site_id=bathymetry.site.id,
        site_name=bathymetry.site.name,
        bathym_yz=bathym_yz,
        bathym_geojson=geojson_linestring(bathym_positions_latlon, props={"bathymetry_id": id})

    )
    return jsonify(data)



@bathymetry_api.errorhandler(ValidationError)
@bathymetry_api.errorhandler(ValueError)
def handle(e):
    """
    Custom error handling for bathymetry API endpoints.

    :param e:
    :return:
    """
    return jsonify({"error": "Invalid input for bathymetry", "message": str(e)}), 400
