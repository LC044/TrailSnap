// An explicit export surface lets Rollup remove Cesium features the footprint
// does not use. The trailsnap-cesium alias also uses this as Vite's development
// prebundle entry; importing cesium directly would retain its entire export list.
export {
  ArcGISTiledElevationTerrainProvider, ArcType, BoundingSphere, Cartesian2,
  Cartesian3, Color, ConstantPositionProperty, ConstantProperty, Credit,
  CustomDataSource, DistanceDisplayCondition, Ellipsoid, EllipsoidTerrainProvider,
  GeographicTilingScheme, HeadingPitchRange, ImageMaterialProperty, JulianDate,
  LabelStyle, Math, NearFarScalar, Occluder, PolylineGlowMaterialProperty,
  Rectangle, SceneMode, SceneTransforms, ScreenSpaceEventHandler,
  ScreenSpaceEventType, UrlTemplateImageryProvider, VerticalOrigin, Viewer,
  WebMercatorTilingScheme,
} from 'cesium'
