from sqlalchemy import Integer, ForeignKey, String, Column, DateTime, Enum, Float, Text
from sqlalchemy.orm import relationship
from sqlalchemy_serializer import SerializerMixin
import pyproj
from models.base import Base


class Bathymetry(Base, SerializerMixin):
    __tablename__ = "bathymetry"
    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("site.id"), nullable=False)
    timestamp = Column(DateTime, nullable=True)
    crs = Column(Integer)
    coordinates = relationship("BathymetryCoordinate", cascade="all, delete")
    site = relationship("Site")
    newsamplefield = Column(Integer, nullable=True)

    def __str__(self):
        return "{}".format(self.id)

    def __repr__(self):
        return "{}".format(self.__str__())

    def get_task_json(self):
        """
        Get dict of coordinates for the JSON content towards the processing node.
        The coordinates are transformed from the bathymetry coordinates to the site projection (EPSG code)

        :return: dict
        """
        # convert bathymetry coordinates to site's EPSG code (keeping z in the same reference system)
        crs_bathymetry = pyproj.CRS.from_epsg(self.crs if self.crs is not None else 4326)  # assume WGS84 latlon if not provided
        crs_site = pyproj.CRS.from_epsg(self.site.position_crs)
        transform = pyproj.Transformer.from_crs(crs_bathymetry, crs_site, always_xy=True)
        coords = [list(transform.transform(c.x, c.y)) + [c.z] for c in self.coordinates]
        return {
            # "coords": list(map(lambda c: [c.x, c.y, c.z], self.coordinates))
            "coords": coords
        }

class BathymetryCoordinate(Base, SerializerMixin):
    __tablename__ = "bathymetrycoordinate"
    id = Column(Integer, primary_key=True)
    bathymetry_id = Column(Integer, ForeignKey("bathymetry.id"), nullable=False)
    x = Column(Float)
    y = Column(Float)
    z = Column(Float)
