from flask import flash, url_for, redirect
from flask_admin.contrib.sqla.filters import BaseSQLAFilter
from flask_admin import expose
from flask_admin.actions import action
from flask_security import current_user
from sqlalchemy.exc import IntegrityError
from models import db
from models.movie import Movie, MovieType, MovieStatus
from models.site import Site
from models.camera import CameraConfig, Camera
from models.ratingcurve import RatingCurve, RatingPoint
from controllers import optimize_rating
from views.general import UserModelView
from views.elements.s3uploadfield import s3UploadField


class FilterMovieBySite(BaseSQLAFilter):

    def apply(self, query, value, alias=None):
        """
        Override to create an appropriate query and apply a filter to said query with the passed value from the filter UI.

        :param query:
        :param value:
        :param alias:
        :return:
        """
        return (
            query
                .filter(Site.id == value)
                .filter(Site.user_id == current_user.id)
        )

    def operation(self):
        """
        Readable operation name. This appears in the middle filter line drop-down

        :return:
        """
        return u"equals"

    def get_options(self, view):
        """
        Override to provide the options for the filter - in this case it's a list of the titles of the Client model.

        :param view:
        :return:
        """
        return [(site.id, site.name) for site in (Site.query.filter_by(user_id=current_user.id).order_by(Site.name) if current_user else [])]

class MovieView(UserModelView):
    column_list = (
        "config.camera.site",
        Movie.file_name,
        Movie.timestamp,
        Movie.actual_water_level,
        Movie.discharge_q05,
        Movie.discharge_q25,
        Movie.discharge_q50,
        Movie.discharge_q75,
        Movie.discharge_q95,
        Movie.status,
    )


    column_descriptions = {
        "timestamp": "User selected time stamp of movie",
        "discharge_q50": "Discharge based on frame-to-frame median velocities",
        "actual_water_level": "Water level as measured on staff gauge in view",
        "status": "Status indicator on level of processing performed",
    }

    column_labels = {"config.camera.site": "Site",
                     "timestamp": "Time stamp",
                     "actual_water_level": "Water level [m]",
                     "discharge_q50": "Median discharge [m3/s]",
                     "status": "Movie status",
                     }
    column_filters = [FilterMovieBySite(column=None, name="Site")]
    column_formatters = dict(
        discharge_q05=lambda v, c, m, p: "{:.3f}".format(m.discharge_q05)
        if m.discharge_q05
        else "",
        discharge_q25=lambda v, c, m, p: "{:.3f}".format(m.discharge_q25)
        if m.discharge_q25
        else "",
        discharge_q50=lambda v, c, m, p: "{:.3f}".format(m.discharge_q50)
        if m.discharge_q50
        else "",
        discharge_q75=lambda v, c, m, p: "{:.3f}".format(m.discharge_q75)
        if m.discharge_q75
        else "",
        discharge_q95=lambda v, c, m, p: "{:.3f}".format(m.discharge_q95)
        if m.discharge_q95
        else "",
    )

    form_columns = ("config", Movie.timestamp, "file_name", Movie.actual_water_level)
    form_extra_fields = {
        "file_name": s3UploadField(
            "File", allowed_extensions=("mkv", "mpeg", "mp4")
        )
    }
    form_args = {
        "config": {
            "query_factory": lambda: CameraConfig.query.join(Camera).join(Site).filter_by(
                user_id=current_user.id
            )
        }
    }
    form_create_rules = ("config", "timestamp", "file_name")

    create_template = "movie/create.html"
    edit_template = "movie/edit.html"
    form_edit_rules = ("timestamp", "actual_water_level")

    details_template = "movie/details.html"
    column_details_list = (
        "config",
        "timestamp",
        "file_name",
        "status",
        "actual_water_level",
        "discharge_q50",
    )

    def get_query(self):
        """
        Don't show movies which are uploaded specifically for the camera config or movies not from this user.

        :return:
        """
        return super(MovieView, self).get_query().filter_by(type=MovieType.MOVIE_TYPE_NORMAL).join(CameraConfig).join(Camera).join(Site).filter_by(user_id=current_user.id)

    def get_one(self, id):
        """
        Don't allow to access a specific movie if it's not from this user.

        :param id:
        :return:
        """
        return super(MovieView, self).get_query().filter_by(id=id).join(CameraConfig).join(Camera).join(Site).filter_by(user_id=current_user.id).one()

    @expose("/")
    def index_view(self):
        """
        Ensure the filter options are always up-to-date.

        :return:
        """
        self._refresh_filters_cache()
        return super(MovieView, self).index_view()

    @action('create_ratingcurve', 'Make rating curve')
    def action_create_ratingcurve(self, ids):
        """
        Custom action in movie list view to create a rating curve with selected movies.

        :param ids: list of movie identifiers
        :return:
        """
        movies = Movie.query.filter(Movie.id.in_(ids)).all()
        site_id = movies[0].config.camera.site_id
        print("#\n#\n#\n#\n#\n#\n#\n#\n#\n#\n#\n")

        # put together a dict of water levels and discharges, remove points that are not completed yet
        for movie in movies:
            valid_ids = [movie.id for movie in movies if (movie.actual_water_level and movie.discharge_q50)]
            rating_points  = dict(
                h=[movie.actual_water_level for movie in movies if (movie.actual_water_level and movie.discharge_q50)],
                Q=[movie.discharge_q50 for movie in movies if (movie.actual_water_level and movie.discharge_q50)],
            )
        print(rating_points)
        # fit rating curve and add curve and points to database
        if len(rating_points["h"]) > 4:
            # get the rating curve
            params = optimize_rating(**rating_points)
            # put parameters into rating table
            rating_curve = RatingCurve(site_id=site_id, **params)
            db.add(rating_curve)
            db.commit()
            db.refresh(rating_curve)
            # make individual rating points
            valid_movies = Movie.query.filter(Movie.id.in_(valid_ids)).all()
            for movie in valid_movies:
                rating_point = RatingPoint(
                    ratingcurve_id=rating_curve.id,
                    movie_id = movie.id,
                )
                db.add(rating_point)
            db.commit()
            db.refresh(rating_curve)
            flash(f"Rating curve with ID {rating_curve.id} stored")
            return redirect(url_for('ratingcurve.edit_view', id=rating_curve.id))

        else:
            flash("There are not enough rating points. Minimum 5 points are required to construct a rating curve", "error")

    def on_model_change(self, form, model, is_created):
        if not is_created:
            if model.actual_water_level != self.previous_water_level:
                model.status = MovieStatus.MOVIE_STATUS_EXTRACTED

                rating_points = RatingPoint.query.filter_by(movie_id=model.id)
                for rating_point in rating_points:
                    rating_curve = RatingCurve.query.get(rating_point.ratingcurve_id)
                    rating_curve.a = None
                    rating_curve.b = None
                    rating_curve.h0 = None
                flash("Movie Will be reprocessed And Rating Curve Will be affected")

    def edit_form(self, obj=None):
        try:
            self.previous_water_level = obj.actual_water_level
        except AttributeError:
            pass

        return UserModelView.edit_form(self, obj)

    def handle_view_exception(self, e):
        """
        Human readable error message for database integrity errors.

        :param e:
        :return:
        """
        if isinstance(e, IntegrityError):
            flash("Movie can\'t be deleted since it\'s being used in a rating curve. You\'ll need to delete that rating curve first.", "error")
            return True

        return super(ModelView, self).handle_view_exception(exc)
