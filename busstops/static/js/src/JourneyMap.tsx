import React from "react";

import Map, {
  Source,
  Layer,
  NavigationControl,
  GeolocateControl,
  Popup,
  MapEvent,
  LayerProps,
  MapLayerMouseEvent,
} from "react-map-gl/maplibre";

import { LngLatBounds } from "maplibre-gl";
import TripTimetable, { TripTime } from "./TripTimetable";
import StopPopup from "./StopPopup";

type VehicleJourneyLocation = {
  coordinates: [number, number];
  delta: number;
  direction: number;
  datetime: string;
};

type Stop = {
  properties: {
    name: string;
    atco_code: string;
  };
  geometry: {
    coordinates: [number, number];
  };
};

type StopTime = {
  atco_code: string;
  name: string;
  aimed_arrival_time: string;
  aimed_departure_time: string;
  minor: boolean;
  heading: number;
  coordinates?: [number, number];
  actual_departure_time: string;
};

export type VehicleJourney = {
  stops: StopTime[];
  locations: VehicleJourneyLocation[];
  next: {
    id: number;
    datetime: string;
  };
  previous: {
    id: number;
    datetime: string;
  };
};

const stopsStyle: LayerProps = {
  id: "stops",
  type: "symbol",
  layout: {
    "icon-rotate": ["+", 45, ["get", "heading"]],
    "icon-image": "stop",
    "icon-allow-overlap": true,
    "icon-ignore-placement": true,
  },
};

const locationsStyle: LayerProps = {
  id: "locations",
  type: "symbol",
  layout: {
    "icon-rotate": ["+", 45, ["get", "heading"]],
    "icon-image": "arrow",
    // "icon-allow-overlap": true,
    // "icon-ignore-placement": true,
    "icon-anchor": "top-left",
  },
};

const routeStyle: LayerProps = {
  type: "line",
  paint: {
    "line-color": "#000",
    "line-opacity": 0.5,
    "line-width": 3,
    "line-dasharray": [2, 2],
  },
};

type LocationPopupProps = {
  location: {
    properties: {
      datetime: string;
    };
    geometry: {
      coordinates: [number, number];
    };
  };
};

function LocationPopup({ location }: LocationPopupProps) {
  const when = new Date(location.properties.datetime);
  return (
    <Popup
      latitude={location.geometry.coordinates[1]}
      longitude={location.geometry.coordinates[0]}
      closeButton={false}
      closeOnClick={false}
      focusAfterOpen={false}
    >
      {when.toTimeString().slice(0, 8)}
    </Popup>
  );
}

type LocationsProps = {
  locations: VehicleJourneyLocation[];
};

type StopsProps = {
  stops: StopTime[];
};

const Locations = React.memo(function Locations({ locations }: LocationsProps) {
  return (
    <React.Fragment>
      <Source
        type="geojson"
        data={{
          type: "LineString",
          coordinates: locations.map((l) => l.coordinates),
        }}
      >
        <Layer {...routeStyle} />
      </Source>

      <Source
        type="geojson"
        data={{
          type: "FeatureCollection",
          features: locations.map((l) => {
            return {
              type: "Feature",
              geometry: {
                type: "Point",
                coordinates: l.coordinates,
              },
              properties: {
                delta: l.delta,
                heading: l.direction,
                datetime: l.datetime,
              },
            };
          }),
        }}
      >
        <Layer {...locationsStyle} />
      </Source>
    </React.Fragment>
  );
});

const Stops = React.memo(function Stops({ stops }: StopsProps) {
  return (
    <Source
      type="geojson"
      data={{
        type: "FeatureCollection",
        features: stops.map((s) => {
          return {
            type: "Feature",
            geometry: {
              type: "Point",
              coordinates: s.coordinates,
            },
            properties: {
              atco_code: s.atco_code,
              name: s.name,
              minor: s.minor,
              heading: s.heading,
              aimed_arrival_time: s.aimed_arrival_time,
              aimed_departure_time: s.aimed_departure_time,
            },
          };
        }),
      }}
    >
      <Layer {...stopsStyle} />
    </Source>
  );
});

type JourneyMapProps = {
  journey?: VehicleJourney;
  loading: boolean;
};

type SidebarProps = {
  journey: VehicleJourney;
  loading: boolean;
  onMouseEnter: (t: TripTime) => void;
};

function Sidebar({ journey, loading, onMouseEnter }: SidebarProps) {
  let className = "trip-timetable map-sidebar";
  if (loading) {
    className += " loading";
  }

  let previousLink, nextLink;
  if (journey) {
    if (journey.previous) {
      previousLink = new Date(journey.previous.datetime)
        .toTimeString()
        .slice(0, 5);
      previousLink = (
        <p className="previous">
          <a href={`#journeys/${journey.previous.id}`}>&larr; {previousLink}</a>
        </p>
      );
    }
    if (journey.next) {
      nextLink = new Date(journey.next.datetime).toTimeString().slice(0, 5);
      nextLink = (
        <p className="next">
          <a href={`#journeys/${journey.next.id}`}>{nextLink} &rarr;</a>
        </p>
      );
    }
  }

  return (
    <div className={className}>
      {previousLink}
      {nextLink}
      {journey.stops ? (
        <TripTimetable
          onMouseEnter={onMouseEnter}
          trip={{
            times: journey.stops.map((stop, i: number) => {
              return {
                id: i,
                stop: {
                  atco_code: stop.atco_code,
                  name: stop.name,
                  location: stop.coordinates,
                },
                timing_status: stop.minor ? "OTH" : "PTP",
                aimed_arrival_time: stop.aimed_arrival_time,
                aimed_departure_time: stop.aimed_departure_time,
                actual_departure_time: stop.actual_departure_time,
              };
            }),
          }}
        />
      ) : null}
    </div>
  );
}

export default function JourneyMap({
  journey,
  loading = false,
}: JourneyMapProps) {
  const darkMode = false;

  const [cursor, setCursor] = React.useState<string>();

  const [clickedLocation, setClickedLocation] =
    React.useState<LocationPopupProps["location"]>();

  const onMouseEnter = React.useCallback((e: MapLayerMouseEvent) => {
    if (e.features?.length) {
      setCursor("pointer");

      for (const feature of e.features) {
        if (feature.layer.id === "locations") {
          setClickedLocation(feature as any as LocationPopupProps["location"]);
          break;
        }
      }
    }
  }, []);

  const onMouseLeave = React.useCallback(() => {
    setCursor(undefined);
    setClickedLocation(undefined);
  }, []);

  const [clickedStop, setClickedStop] = React.useState<Stop>();

  const handleMapClick = React.useCallback((e: MapLayerMouseEvent) => {
    if (e.features?.length) {
      for (const feature of e.features) {
        if (feature.layer.id === "stops") {
          setClickedStop(feature as any as Stop);
          break;
        }
      }
    } else {
      setClickedStop(undefined);
    }
  }, []);

  const handleRowHover = React.useCallback((a: TripTime) => {
    if (a.stop.location && a.stop.atco_code) {
      setClickedStop({
        properties: {
          atco_code: a.stop.atco_code,
          name: a.stop.name,
        },
        geometry: {
          coordinates: a.stop.location,
        },
      });
    }
  }, []);

  const mapRef = React.useRef<any>();

  const handleMapLoad = React.useCallback((event: MapEvent) => {
    const map = event.target;
    mapRef.current = map;
    map.keyboard.disableRotation();
    map.touchZoomRotate.disableRotation();

    map.loadImage("/static/route-stop-marker.png", (error, image) => {
      if (error) throw error;
      if (image) {
        map.addImage("stop", image, {
          pixelRatio: 2,
        });
      }
    });

    map.loadImage("/static/arrow.png", (error, image) => {
      if (error) throw error;
      if (image) {
        map.addImage("arrow", image, {
          pixelRatio: 2,
        });
      }
    });
  }, []);

  const bounds = React.useMemo((): LngLatBounds | undefined => {
    if (journey) {
      const _bounds = new LngLatBounds();
      if (journey.locations) {
        for (const item of journey.locations) {
          _bounds.extend(item.coordinates);
        }
      }
      if (journey.stops) {
        for (const item of journey.stops) {
          if (item.coordinates) {
            _bounds.extend(item.coordinates);
          }
        }
      }
      return _bounds;
    }
  }, [journey]);

  React.useEffect(() => {
    if (bounds && mapRef.current) {
      mapRef.current.fitBounds(bounds, {
        padding: 50,
      });
    }
  }, [bounds]);

  if (!journey) {
    return <div className="sorry">Loading…</div>;
  }

  return (
    <React.Fragment>
      <div className="journey-map has-sidebar">
        <Map
          dragRotate={false}
          touchPitch={false}
          pitchWithRotate={false}
          maxZoom={18}
          initialViewState={{
            bounds: bounds,
            fitBoundsOptions: {
              padding: 50,
            },
          }}
          cursor={cursor}
          onMouseEnter={onMouseEnter}
          onMouseMove={onMouseEnter}
          onMouseLeave={onMouseLeave}
          mapStyle={
            darkMode
              ? "https://tiles.stadiamaps.com/styles/alidade_smooth_dark.json"
              : "https://tiles.stadiamaps.com/styles/alidade_smooth.json"
          }
          RTLTextPlugin={""}
          onClick={handleMapClick}
          onLoad={handleMapLoad}
          interactiveLayerIds={["stops", "locations"]}
        >
          <NavigationControl showCompass={false} />
          <GeolocateControl />

          {journey.stops ? <Stops stops={journey.stops} /> : null}

          {journey.locations ? (
            <Locations locations={journey.locations} />
          ) : null}

          {clickedStop ? (
            <StopPopup
              item={{
                properties: {
                  url: `/stops/${clickedStop.properties.atco_code}`,
                  name: clickedStop.properties.name,
                },
                geometry: clickedStop.geometry,
              }}
              onClose={() => setClickedStop(undefined)}
            />
          ) : null}

          {clickedLocation ? (
            <LocationPopup location={clickedLocation} />
          ) : null}
        </Map>
      </div>
      <Sidebar
        loading={loading}
        journey={journey}
        onMouseEnter={handleRowHover}
      />
    </React.Fragment>
  );
}