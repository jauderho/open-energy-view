"""API endpoints for viewing data."""
from flask import jsonify
import json
from flask_restful import Resource, reqparse
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    jwt_refresh_token_required,
    get_jwt_identity,
    set_access_cookies,
    set_refresh_cookies,
    unset_jwt_cookies,
)

from . import models
from . import bcrypt
from . import db
from .database import EnergyHistory

auth_parser = reqparse.RequestParser()
auth_parser.add_argument("email", help="Cannot be blank", required=True)
auth_parser.add_argument("password", help="Cannot be blank", required=True)

get_data_parser = reqparse.RequestParser()
get_data_parser.add_argument("source", required=False)
get_data_parser.add_argument("name", required=False)
get_data_parser.add_argument("thirdPartyId", required=False)
get_data_parser.add_argument("clientId", required=False)
get_data_parser.add_argument("clientSecret", required=False)


class AuthToken(Resource):
    def make_cookies(self, email):
        access_token = create_access_token(identity=email)
        refresh_token = create_refresh_token(identity=email)
        resp = jsonify({"login": True})
        set_access_cookies(resp, access_token)
        set_refresh_cookies(resp, refresh_token)
        return resp


class Register(AuthToken):
    def post(self):
        data = auth_parser.parse_args()
        if models.User.find_by_email(data["email"]):
            return {"message": f'User {data["email"]} already exists.'}, 403

        new_user = models.User(
            email=data["email"],
            password=bcrypt.generate_password_hash(
                data["password"]).decode("utf-8"),
        )
        try:
            new_user.save_to_db()
            return self.make_cookies(data["email"])
        except Exception as e:
            return {"message": str(e)}, 500
        finally:
            pass


class AddPgeSource(AuthToken):
    @jwt_required
    def post(self):
        print(get_data_parser.parse_args())
        user = db.session.query(models.User).filter_by(
            email=get_jwt_identity()).first()
        data = get_data_parser.parse_args()
        new_account = models.PgeSmd(
            u_id=user.id,
            friendly_name=data["name"],
            reg_type="self",
            third_party_id=data["thirdPartyId"],
            client_id=data["clientId"],
            client_secret=data["clientSecret"]
        )
        new_account.save_to_db()
        print(new_account.id)


class UserLogin(AuthToken):
    def post(self):
        data = auth_parser.parse_args()
        current_user = models.User.find_by_email(data["email"])
        if not current_user:
            return {"message": "Bad credentials"}, 401

        if bcrypt.check_password_hash(current_user.password, data["password"]):
            return self.make_cookies(data["email"])
        else:
            return {"message": "Bad credentials"}, 401


class UserLogout(Resource):
    def post(self):
        resp = jsonify({"logout": True})
        unset_jwt_cookies(resp)
        return resp


class TokenRefresh(Resource):
    @jwt_refresh_token_required
    def post(self):
        current_user = get_jwt_identity()
        access_token = create_access_token(identity=current_user)
        resp = jsonify({"refresh": True})
        set_access_cookies(resp, access_token)
        return resp


class AllUsers(Resource):
    def get(self):
        return models.User.return_all()

    def delete(self):
        return models.User.delete_all()


class SecretResource(Resource):
    @jwt_required
    def get(self):
        username = get_jwt_identity()
        return jsonify({"hello": "from {}".format(username)})


class GetSources(Resource):
    @jwt_required
    def post(self):
        user = db.session.query(models.User).filter_by(
            email=get_jwt_identity()).first()
        sources_entries = (
            db.session.query(models.PgeSmd)
            .with_parent(user)
            .all()
        )
        sources = list(map(lambda x: x.friendly_name, sources_entries))
        return(sources)


class GetPartitionOptions(Resource):
    @jwt_required
    def post(self):
        data = get_data_parser.parse_args()
        if not data['source'] or data['source'] == 'None':
            return
        user = db.session.query(models.User).filter_by(
            email=get_jwt_identity()).first()
        source = (
            db.session.query(models.PgeSmd)
            .filter_by(friendly_name=data["source"])
            .with_parent(user)
            .first()
        )
        return source.partition_options


class GetEnergyHistory(Resource):
    @jwt_required
    def post(self):
        data = get_data_parser.parse_args()
        if not data['source'] or data['source'] == 'None':
            return
        user = db.session.query(models.User).filter_by(
            email=get_jwt_identity()).first()
        source = (
            db.session.query(models.PgeSmd)
            .filter_by(friendly_name=data["source"])
            .with_parent(user)
            .first()
        )
        hours = db.session.query(models.Hour).filter_by(
            pge_id=source.third_party_id).all()
        database = ','.join([
            f'{entry.start//3600}{entry.watt_hours}' for entry in hours
            ]
        )
        response = {
            "utility": "pge",
            "interval": 3600,
            "friendlyName": data['source'],
            "lastUpdate": None,
            "partitionOptions": source.partition_options,
            "database": database
        }
        return response


class GetHours(Resource):
    @jwt_required
    def post(self):
        data = get_data_parser.parse_args()
        if not data['source'] or data['source'] == 'None':
            return
        user = db.session.query(models.User).filter_by(
            email=get_jwt_identity()).first()
        source = (
            db.session.query(models.PgeSmd)
            .filter_by(friendly_name=data["source"])
            .with_parent(user)
            .first()
        )
        hours = db.session.query(models.Hour).filter_by(
            pge_id=source.third_party_id).all()
        return ','.join([
            f'{entry.start//3600}{entry.watt_hours}' for entry in hours
            ]
        )

class GetDatabase(Resource):
    @jwt_required
    def post(self):
        data = get_data_parser.parse_args()
        if not data['source'] or data['source'] == 'None':
            return
        user = db.session.query(models.User).filter_by(
            email=get_jwt_identity()).first()
        source = (
            db.session.query(models.PgeSmd)
            .filter_by(friendly_name=data["source"])
            .with_parent(user)
            .first()
        )
        eh = EnergyHistory(path="/test/data/energy_history_test.db")
        if eh.save_json(source.third_party_id):
            eh.cursor.close()
            return json.dumps(eh.json)
        eh.cursor.close()


class AddDemoPge(Resource):
    @jwt_required
    def post(self, friendly_name="PG&E", reg_type="Self Access"):
        user = db.session.query(models.User).filter_by(
            email=get_jwt_identity()).first()
        new_account = models.PgeSmd(
            id=50916, u_id=user.id, friendly_name=friendly_name
        )
        new_account.save_to_db()
        print(new_account.id)
