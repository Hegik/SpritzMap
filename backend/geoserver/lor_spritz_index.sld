<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor version="1.0.0"
  xmlns="http://www.opengis.net/sld"
  xmlns:ogc="http://www.opengis.net/ogc"
  xmlns:xlink="http://www.w3.org/1999/xlink"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.opengis.net/sld
    http://schemas.opengis.net/sld/1.0.0/StyledLayerDescriptor.xsd">
  <NamedLayer>
    <Name>lor_price_summary</Name>
    <UserStyle>
      <Title>Spritz Index</Title>
      <FeatureTypeStyle>

        <!-- LORs with data -->
        <Rule>
          <Name>with_data</Name>
          <ogc:Filter>
            <ogc:Not>
              <ogc:PropertyIsNull>
                <ogc:PropertyName>spritz_index</ogc:PropertyName>
              </ogc:PropertyIsNull>
            </ogc:Not>
          </ogc:Filter>
          <PolygonSymbolizer>
            <Fill>
              <CssParameter name="fill">
                <ogc:PropertyName>drink_color</ogc:PropertyName>
              </CssParameter>
              <CssParameter name="fill-opacity">
                <ogc:Function name="Interpolate">
                  <ogc:PropertyName>spritz_index</ogc:PropertyName>
                  <ogc:Literal>0</ogc:Literal>
                  <ogc:Literal>0.08</ogc:Literal>
                  <ogc:Literal>100</ogc:Literal>
                  <ogc:Literal>0.80</ogc:Literal>
                  <ogc:Literal>linear</ogc:Literal>
                </ogc:Function>
              </CssParameter>
            </Fill>
            <Stroke>
              <CssParameter name="stroke">
                <ogc:PropertyName>drink_color</ogc:PropertyName>
              </CssParameter>
              <CssParameter name="stroke-width">0.5</CssParameter>
              <CssParameter name="stroke-opacity">0.3</CssParameter>
            </Stroke>
          </PolygonSymbolizer>
        </Rule>

        <!-- LORs without data: invisible -->
        <Rule>
          <Name>no_data</Name>
          <ogc:Filter>
            <ogc:PropertyIsNull>
              <ogc:PropertyName>spritz_index</ogc:PropertyName>
            </ogc:PropertyIsNull>
          </ogc:Filter>
          <PolygonSymbolizer>
            <Fill>
              <CssParameter name="fill">#000000</CssParameter>
              <CssParameter name="fill-opacity">0</CssParameter>
            </Fill>
            <Stroke>
              <CssParameter name="stroke-opacity">0</CssParameter>
            </Stroke>
          </PolygonSymbolizer>
        </Rule>

      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
