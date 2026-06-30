from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, not_
from app.dependencies import get_db, BaseResponse
from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.schemas.guess_city import CityCoordinate, GuessRequest, GuessResult
from app.utils.geo import calculate_haversine_distance, calculate_bearing, get_compass_direction
from datetime import datetime
import random

router = APIRouter()

@router.get("/random", response_model=BaseResponse)
def get_random_photo(db: Session = Depends(get_db)):
    """
    Get a random photo for the guess city game.
    Exclude the Top 1 city and prioritize photos older than 1 year.
    """
    # Find the top 1 city
    top_city_row = db.query(
        PhotoMetadata.city, func.count(PhotoMetadata.photo_id).label("count")
    ).filter(PhotoMetadata.city.isnot(None), PhotoMetadata.city != "")\
    .group_by(PhotoMetadata.city)\
    .order_by(desc("count"))\
    .first()

    top_city = top_city_row.city if top_city_row else None

    # Base query for valid photos (has location, not deleted)
    query = db.query(Photo).join(PhotoMetadata, Photo.id == PhotoMetadata.photo_id)\
        .filter(Photo.is_deleted == False)\
        .filter(PhotoMetadata.city.isnot(None), PhotoMetadata.city != "")

    if top_city:
        query = query.filter(PhotoMetadata.city != top_city)

    # Prioritize > 1 year old
    one_year_ago = datetime.now().replace(year=datetime.now().year - 1)
    
    # Get old photos
    old_photos = query.filter(Photo.photo_time < one_year_ago).all()
    
    if old_photos:
        chosen = random.choice(old_photos)
    else:
        # Fallback to any photo
        all_photos = query.all()
        if not all_photos:
            return BaseResponse(code=404, msg="No suitable photos found")
        chosen = random.choice(all_photos)

    # We need to return enough info for the frontend
    # Since it's a guess game, we don't return the actual city.
    # We return the photo id, url (file_path can be used to construct url, but typically frontend uses /api/medias/thumbnail/{id})
    # and maybe photo_time.
    
    return BaseResponse(code=0, msg="success", data={
        "id": str(chosen.id),
        "photo_time": chosen.photo_time.isoformat() if chosen.photo_time else None
    })

@router.get("/cities", response_model=BaseResponse)
def get_cities(db: Session = Depends(get_db)):
    """
    Get a list of unique cities with their average coordinates.
    """
    results = db.query(
        PhotoMetadata.city,
        func.avg(PhotoMetadata.latitude).label("avg_lat"),
        func.avg(PhotoMetadata.longitude).label("avg_lon")
    ).filter(
        PhotoMetadata.city.isnot(None), 
        PhotoMetadata.city != "",
        PhotoMetadata.latitude.isnot(None),
        PhotoMetadata.longitude.isnot(None)
    ).group_by(PhotoMetadata.city).all()

    cities = [
        {
            "city": row.city,
            "latitude": float(row.avg_lat) if row.avg_lat else 0.0,
            "longitude": float(row.avg_lon) if row.avg_lon else 0.0
        } for row in results
    ]

    return BaseResponse(code=0, msg="success", data=cities)

@router.post("/guess", response_model=BaseResponse)
def guess_city(req: GuessRequest, db: Session = Depends(get_db)):
    """
    Verify the guessed city.
    """
    metadata = db.query(PhotoMetadata).filter(PhotoMetadata.photo_id == req.photo_id).first()
    if not metadata or not metadata.city:
        return BaseResponse(code=404, msg="Photo or location not found")

    actual_city = metadata.city
    correct = (actual_city == req.guess_city)

    # Get coordinates of the guessed city from average of all photos in that city
    guess_city_coords = db.query(
        func.avg(PhotoMetadata.latitude).label("lat"),
        func.avg(PhotoMetadata.longitude).label("lon")
    ).filter(PhotoMetadata.city == req.guess_city).first()

    distance = 0.0
    bearing = 0.0
    direction = ""

    if not correct and guess_city_coords and guess_city_coords.lat is not None:
        guess_lat = float(guess_city_coords.lat)
        guess_lon = float(guess_city_coords.lon)
        actual_lat = float(metadata.latitude)
        actual_lon = float(metadata.longitude)

        distance = calculate_haversine_distance(guess_lat, guess_lon, actual_lat, actual_lon)
        bearing = calculate_bearing(guess_lat, guess_lon, actual_lat, actual_lon)
        direction = get_compass_direction(bearing)

    result = GuessResult(
        correct=correct,
        actual_city=actual_city,
        distance_km=distance,
        bearing=bearing,
        direction=direction
    )

    return BaseResponse(code=0, msg="success", data=result.dict())
