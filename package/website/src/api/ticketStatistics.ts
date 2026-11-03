import request from "@/utils/request";
import type { StationListResponse } from "@/api/railway";

export interface MapFeature {
  type: "Feature";
  properties: {
    name?: string;
    fullname?: string;
    cp?: number[];
    center?: number[];
    centroid?: number[];
  };
  geometry: { type: string; coordinates: unknown };
}
export interface TicketMap {
  type: "FeatureCollection";
  features: MapFeature[];
}

export const ticketStatisticsApi = {
  async map(signal?: AbortSignal) {
    return (
      await request.get<TicketMap>("/api/medias/geojson", {
        params: { level: "city" },
        signal,
        silentError: true,
      })
    ).data;
  },
  async stationCities() {
    const cities = new Map<string, string>();
    let count = 0;
    for (let page = 1; ; page++) {
      const data = (
        await request.get<StationListResponse>("/api/railway/stations", {
          params: { page, page_size: 2000 },
          silentError: true,
        })
      ).data;
      if (!data?.list?.length) break;
      for (const station of data.list)
        if (station.city) cities.set(station.station_name, station.city);
      count += data.list.length;
      if (count >= data.total) break;
    }
    return cities;
  },
};
