import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API, timeout: 30000 });

export const fetchDimensions = () => api.get("/dimensions").then((r) => r.data.dimensions);

export const geocode = (q) =>
  api.get("/geocode", { params: { q, limit: 8 } }).then((r) => r.data.results);

export const reverseGeocode = (lat, lng) =>
  api.get("/reverse", { params: { lat, lng } }).then((r) => r.data.display_name);

export const computeRoute = (origin, destination, dimensions, criticalZones = []) =>
  api
    .post("/route", {
      origin,
      destination,
      dimensions,
      critical_zones: criticalZones,
    })
    .then((r) => r.data);
