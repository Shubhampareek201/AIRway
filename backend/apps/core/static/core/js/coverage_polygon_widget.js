(function () {
  "use strict";

  function initialiseCoverageMap(root) {
    const textarea = root.querySelector("textarea.airway-coverage-json");
    const mapElement = root.querySelector(".airway-coverage-map");
    if (!textarea || !mapElement || mapElement.dataset.initialised === "true") return;
    if (!window.L || !L.Control || !L.Control.Draw) {
      root.querySelector(".airway-coverage-status").textContent =
        "Map tools could not load. Refresh the page and check the internet connection.";
      return;
    }
    mapElement.dataset.initialised = "true";

    const status = root.querySelector(".airway-coverage-status");
    const searchInput = root.querySelector(".airway-coverage-search");
    const map = L.map(mapElement).setView([
      Number(mapElement.dataset.mapLat || 24.93),
      Number(mapElement.dataset.mapLng || 75.59)
    ], 13);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    const boundaryLayer = new L.FeatureGroup();
    map.addLayer(boundaryLayer);

    function setStatus(message) {
      status.textContent = message;
    }

    function updateCentre(geometry) {
      const ring = geometry && geometry.coordinates && geometry.coordinates[0];
      if (!ring || !ring.length) return;
      const usable = ring.slice(0, -1);
      if (!usable.length) return;
      const longitude = usable.reduce((sum, point) => sum + Number(point[0]), 0) / usable.length;
      const latitude = usable.reduce((sum, point) => sum + Number(point[1]), 0) / usable.length;
      const latInput = document.getElementById("id_latitude");
      const lngInput = document.getElementById("id_longitude");
      if (latInput) {
        latInput.value = latitude.toFixed(6);
        latInput.dispatchEvent(new Event("change", { bubbles: true }));
      }
      if (lngInput) {
        lngInput.value = longitude.toFixed(6);
        lngInput.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }

    function saveBoundary(layer) {
      boundaryLayer.clearLayers();
      boundaryLayer.addLayer(layer);
      const geometry = layer.toGeoJSON().geometry;
      textarea.value = JSON.stringify(geometry);
      updateCentre(geometry);
      setStatus("Boundary ready. Review the outline, then save the Zone.");
    }

    const drawControl = new L.Control.Draw({
      position: "topleft",
      draw: {
        polygon: {
          allowIntersection: false,
          showArea: true,
          shapeOptions: { color: "#6d45c7", weight: 3, fillOpacity: 0.16 }
        },
        polyline: false,
        rectangle: false,
        circle: false,
        circlemarker: false,
        marker: false
      },
      edit: { featureGroup: boundaryLayer, remove: true }
    });
    map.addControl(drawControl);

    map.on(L.Draw.Event.CREATED, function (event) {
      saveBoundary(event.layer);
    });
    map.on(L.Draw.Event.EDITED, function (event) {
      event.layers.eachLayer(saveBoundary);
    });
    map.on(L.Draw.Event.DELETED, function () {
      textarea.value = "";
      const latInput = document.getElementById("id_latitude");
      const lngInput = document.getElementById("id_longitude");
      if (latInput) latInput.value = "";
      if (lngInput) lngInput.value = "";
      setStatus("Boundary removed. Draw a new service-area polygon before saving.");
    });

    function fitBoundary() {
      if (boundaryLayer.getLayers().length) {
        map.fitBounds(boundaryLayer.getBounds(), { padding: [24, 24] });
      }
    }

    root.querySelector(".airway-coverage-fit-button").addEventListener("click", fitBoundary);
    root.querySelector(".airway-coverage-search-button").addEventListener("click", async function () {
      const query = searchInput.value.trim();
      if (!query) {
        setStatus("Enter a place or landmark to search.");
        return;
      }
      setStatus("Searching map...");
      try {
        const url = "https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q=" + encodeURIComponent(query);
        const response = await fetch(url, { headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error("Search service unavailable");
        const results = await response.json();
        if (!results.length) {
          setStatus("No matching place found. Try another spelling or landmark.");
          return;
        }
        map.setView([Number(results[0].lat), Number(results[0].lon)], 14);
        setStatus("Map moved to " + (results[0].display_name || query) + ". Now draw the service boundary.");
      } catch (error) {
        setStatus("Could not search right now. You can still zoom and pan the map manually.");
      }
    });

    if (textarea.value.trim()) {
      try {
        const geometry = JSON.parse(textarea.value);
        if (geometry && geometry.type === "Polygon") {
          const layer = L.geoJSON(geometry, {
            style: { color: "#6d45c7", weight: 3, fillOpacity: 0.16 }
          });
          layer.eachLayer(function (item) { boundaryLayer.addLayer(item); });
          fitBoundary();
          setStatus("Existing service boundary loaded. You can edit it on the map.");
        }
      } catch (error) {
        setStatus("Existing polygon JSON is invalid. Draw a fresh boundary to replace it.");
      }
    }
    window.setTimeout(function () { map.invalidateSize(); }, 250);
  }

  function initialiseAll() {
    document.querySelectorAll(".airway-coverage-widget").forEach(initialiseCoverageMap);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialiseAll);
  } else {
    initialiseAll();
  }
})();
