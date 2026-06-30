import request from '@/utils/request'

export interface GuessCityPhoto {
  id: string
  photo_time: string | null
}

export interface CityCoordinate {
  city: string
  latitude: number
  longitude: number
}

export interface GuessRequest {
  photo_id: string
  guess_city: string
}

export interface GuessResult {
  correct: boolean
  actual_city: string
  distance_km: number
  bearing: number
  direction: string
}

export const guessCityApi = {
  /**
   * Get a random photo for the game
   */
  getRandomPhoto() {
    return request.get<GuessCityPhoto>('/api/guess-city/random')
  },

  /**
   * Get all available cities
   */
  getCities() {
    return request.get<CityCoordinate[]>('/api/guess-city/cities')
  },

  /**
   * Verify the guessed city
   */
  guessCity(data: GuessRequest) {
    return request.post<GuessResult>('/api/guess-city/guess', data)
  }
}
