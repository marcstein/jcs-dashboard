#!/usr/bin/env python
"""Generate heatmap visualizations for client and revenue data by zip code."""

import folium
from folium.plugins import HeatMap
import json
from pathlib import Path
from firm_analytics import FirmAnalytics, format_currency

# Zip code coordinates for St. Louis metro area (approximate centers)
# This is a subset - we'll use a geocoding approach for unknown zips
ZIP_COORDS = {
    # St. Louis City
    "63101": (38.6270, -90.1994), "63102": (38.6318, -90.1884), "63103": (38.6357, -90.2173),
    "63104": (38.6159, -90.2154), "63106": (38.6474, -90.2065), "63107": (38.6653, -90.2119),
    "63108": (38.6478, -90.2610), "63109": (38.5886, -90.2887), "63110": (38.6175, -90.2451),
    "63111": (38.5656, -90.2619), "63112": (38.6616, -90.2879), "63113": (38.6593, -90.2380),
    "63115": (38.6775, -90.2434), "63116": (38.5811, -90.2623), "63118": (38.5920, -90.2252),
    "63119": (38.5901, -90.3452), "63120": (38.6909, -90.2619), "63123": (38.5430, -90.3215),
    "63125": (38.5213, -90.2989), "63128": (38.4896, -90.3700), "63129": (38.4640, -90.3200),
    "63130": (38.6685, -90.3249), "63132": (38.6790, -90.3582), "63133": (38.6879, -90.3040),
    "63134": (38.7055, -90.3403), "63135": (38.7479, -90.2929), "63136": (38.7402, -90.2565),
    "63137": (38.7558, -90.2166), "63138": (38.7903, -90.1885), "63139": (38.6109, -90.2959),
    "63143": (38.6141, -90.3242), "63144": (38.6267, -90.3508), "63146": (38.6972, -90.4375),

    # St. Louis County
    "63005": (38.5587, -90.6523), "63011": (38.5969, -90.5377), "63017": (38.6479, -90.4827),
    "63021": (38.5728, -90.4839), "63022": (38.5833, -90.5167), "63024": (38.5265, -90.5265),
    "63025": (38.4709, -90.5875), "63026": (38.5053, -90.4425), "63031": (38.8018, -90.3196),
    "63033": (38.7862, -90.2539), "63034": (38.8175, -90.2304), "63040": (38.6049, -90.6206),
    "63042": (38.7564, -90.3983), "63043": (38.7200, -90.4308), "63044": (38.7582, -90.4514),
    "63045": (38.7497, -90.4886), "63074": (38.7304, -90.3863), "63088": (38.4980, -90.5785),
    "63114": (38.6987, -90.3619), "63117": (38.6411, -90.3127), "63121": (38.7036, -90.2875),
    "63122": (38.5805, -90.3816), "63124": (38.6496, -90.3570), "63126": (38.5525, -90.3719),
    "63127": (38.5296, -90.4000), "63131": (38.6185, -90.4377), "63141": (38.6665, -90.4525),
    "63145": (38.6910, -90.4147), "63146": (38.6972, -90.4375),

    # St. Charles County
    "63301": (38.7857, -90.4974), "63303": (38.7520, -90.5167), "63304": (38.7217, -90.5650),
    "63366": (38.7987, -90.6765), "63367": (38.8131, -90.7253), "63368": (38.7684, -90.7369),
    "63373": (38.9319, -90.4008), "63376": (38.7636, -90.5731), "63385": (38.8067, -90.8564),
    "63386": (38.8883, -90.6614),

    # Jefferson County
    "63010": (38.4194, -90.3714), "63012": (38.3619, -90.3917), "63016": (38.3544, -90.5642),
    "63019": (38.2775, -90.3836), "63020": (38.1317, -90.4394), "63023": (38.2900, -90.4467),
    "63028": (38.1847, -90.3869), "63048": (38.4322, -90.4356), "63049": (38.4556, -90.4708),
    "63050": (38.2036, -90.5631), "63051": (38.3231, -90.5189), "63052": (38.3856, -90.3483),
    "63053": (38.2525, -90.5758), "63057": (38.2008, -90.4767), "63069": (38.3031, -90.5936),
    "63070": (38.2369, -90.4072),

    # Franklin County
    "63014": (38.4708, -91.1489), "63015": (38.4361, -90.8481), "63038": (38.5319, -90.6811),
    "63039": (38.4583, -90.8422), "63041": (38.4114, -90.8064), "63055": (38.3811, -90.8892),
    "63056": (38.4031, -90.9428), "63060": (38.3572, -90.7933), "63061": (38.3183, -90.8589),
    "63068": (38.4369, -91.0375), "63069": (38.3031, -90.5936), "63071": (38.3536, -90.9167),
    "63072": (38.4017, -90.7136), "63077": (38.3744, -90.9958), "63084": (38.4206, -90.9086),
    "63089": (38.5197, -90.8614), "63090": (38.4250, -90.8903),

    # Warren County
    "63343": (38.9328, -90.9953), "63344": (38.8606, -91.0317), "63348": (38.7628, -90.9481),
    "63349": (38.8467, -90.9519), "63357": (38.7403, -91.0892), "63359": (38.9483, -91.1308),
    "63377": (38.8942, -91.0861), "63379": (38.8275, -90.8808), "63381": (38.8019, -91.0478),
    "63383": (38.7619, -91.1811), "63389": (38.9542, -90.8850), "63390": (38.7911, -90.9903),

    # Lincoln County
    "63334": (39.0369, -90.9481), "63336": (39.1089, -90.7950), "63341": (38.7778, -90.7553),
    "63347": (39.0803, -90.7633), "63351": (39.0083, -91.0919), "63362": (39.0881, -90.9739),
    "63369": (38.9422, -90.7828), "63383": (38.7619, -91.1811),

    # Crawford/Phelps County (Rolla area)
    "65401": (37.9514, -91.7711), "65409": (37.9539, -91.7729),
    "65436": (37.8100, -91.7447), "65438": (37.6169, -91.5364), "65440": (37.8550, -91.9539),
    "65453": (37.8322, -91.5286), "65456": (37.7742, -91.6631), "65461": (37.9514, -91.9083),
    "65462": (37.9267, -92.0708), "65466": (37.6083, -91.3583), "65473": (37.7267, -92.1042),
    "65479": (37.6750, -91.9208), "65529": (37.9581, -91.4269), "65534": (37.7811, -91.8981),
    "65536": (37.7839, -92.1342), "65550": (37.8164, -91.9489), "65556": (37.8050, -91.6806),
    "65560": (37.6897, -91.5039), "65564": (37.5500, -91.6833), "65565": (37.8308, -91.2067),
    "65566": (37.8047, -91.1028), "65580": (37.9533, -91.5658), "65582": (38.0136, -91.7108),
    "65583": (37.8269, -92.0900), "65584": (37.8411, -92.1061), "65588": (37.4875, -91.3500),

    # Other Missouri
    "63005": (38.5587, -90.6523), "63055": (38.3811, -90.8892),
    "65202": (38.9717, -92.3258), "65203": (38.9206, -92.3561),  # Columbia

    # Illinois (Metro East)
    "62002": (38.8906, -90.1842), "62010": (38.8694, -90.0933), "62018": (38.9258, -90.1650),
    "62024": (38.8058, -90.0961), "62025": (38.7997, -89.9517), "62026": (38.7956, -89.9958),
    "62034": (38.7378, -89.9308), "62040": (38.7236, -90.0842), "62048": (38.6722, -90.1500),
    "62059": (38.5417, -90.1733), "62060": (38.6003, -90.1606), "62061": (38.5772, -90.2072),
    "62062": (38.7336, -89.9975), "62067": (38.7883, -90.0975), "62071": (38.5097, -90.1767),
    "62084": (38.8339, -90.0717), "62087": (38.8475, -90.0583), "62090": (38.5786, -90.1808),
    "62095": (38.7542, -90.0036), "62201": (38.6203, -90.1308), "62203": (38.5839, -90.1094),
    "62204": (38.6178, -90.0936), "62205": (38.6064, -90.1039), "62206": (38.5500, -90.1350),
    "62207": (38.5933, -90.1253), "62208": (38.5956, -90.0386), "62220": (38.5203, -89.9986),
    "62221": (38.5419, -90.0042), "62223": (38.5642, -90.0778), "62225": (38.5447, -89.8575),
    "62226": (38.5958, -89.9339), "62232": (38.6314, -89.9586), "62234": (38.6494, -89.9847),
    "62236": (38.4869, -90.1775), "62239": (38.5456, -90.1853), "62240": (38.5067, -90.2128),
    "62243": (38.4347, -89.9119), "62249": (38.8372, -89.8175), "62254": (38.5550, -89.7906),
    "62258": (38.4581, -89.9253), "62260": (38.4253, -90.1839), "62264": (38.3386, -89.9331),
    "62269": (38.6214, -89.8547), "62281": (38.7308, -89.8208), "62282": (38.3553, -89.8208),
    "62285": (38.3722, -90.0575), "62293": (38.6647, -89.7547), "62294": (38.6981, -89.9894),
    "62298": (38.3281, -90.1942),
}


def get_zip_coords(zip_code: str) -> tuple:
    """Get coordinates for a zip code, return None if unknown."""
    # Clean zip code
    zip_code = str(zip_code).strip()[:5]
    return ZIP_COORDS.get(zip_code)


def generate_client_heatmap(output_path: str = "reports/clients_heatmap.html"):
    """Generate heatmap of clients by zip code."""
    analytics = FirmAnalytics()
    zip_clients = analytics.get_clients_by_zip_code()

    # Build heat data
    heat_data = []
    missing_zips = []

    for zip_code, count in zip_clients.items():
        coords = get_zip_coords(zip_code)
        if coords:
            # Weight by client count
            heat_data.append([coords[0], coords[1], count])
        else:
            missing_zips.append((zip_code, count))

    # Create map centered on St. Louis
    m = folium.Map(location=[38.6270, -90.1994], zoom_start=10)

    # Add heatmap layer
    HeatMap(
        heat_data,
        min_opacity=0.3,
        max_zoom=13,
        radius=25,
        blur=15,
        gradient={0.4: 'blue', 0.65: 'lime', 0.8: 'yellow', 1: 'red'}
    ).add_to(m)

    # Add markers for top zip codes
    top_zips = list(zip_clients.items())[:20]
    for zip_code, count in top_zips:
        coords = get_zip_coords(zip_code)
        if coords:
            folium.CircleMarker(
                location=coords,
                radius=min(count / 2, 30),
                popup=f"{zip_code}: {count} clients",
                color='darkblue',
                fill=True,
                fillOpacity=0.7
            ).add_to(m)

    # Add title
    title_html = '''
    <div style="position: fixed; top: 10px; left: 50px; z-index: 1000;
                background-color: white; padding: 10px; border-radius: 5px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.3);">
        <h3 style="margin: 0;">JCS Law Firm - Clients by Zip Code</h3>
        <p style="margin: 5px 0 0 0; font-size: 12px;">
            Total zip codes: {total_zips} | Mapped: {mapped} | Missing coords: {missing}
        </p>
    </div>
    '''.format(total_zips=len(zip_clients), mapped=len(heat_data), missing=len(missing_zips))
    m.get_root().html.add_child(folium.Element(title_html))

    # Save
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    m.save(output_path)
    print(f"Client heatmap saved to {output_path}")

    if missing_zips:
        print(f"  Note: {len(missing_zips)} zip codes missing coordinates")

    return output_path


def generate_revenue_heatmap(output_path: str = "reports/revenue_heatmap.html"):
    """Generate heatmap of revenue by zip code."""
    analytics = FirmAnalytics()
    zip_revenue = analytics.get_revenue_by_zip_code()

    # Build heat data (weighted by collected revenue)
    heat_data = []
    missing_zips = []

    for zip_code, data in zip_revenue.items():
        coords = get_zip_coords(zip_code)
        if coords:
            # Weight by collected revenue (scale down for heatmap)
            weight = data['collected'] / 1000  # Scale to thousands
            heat_data.append([coords[0], coords[1], weight])
        else:
            missing_zips.append((zip_code, data))

    # Create map centered on St. Louis
    m = folium.Map(location=[38.6270, -90.1994], zoom_start=10)

    # Add heatmap layer
    HeatMap(
        heat_data,
        min_opacity=0.3,
        max_zoom=13,
        radius=25,
        blur=15,
        gradient={0.4: 'blue', 0.65: 'lime', 0.8: 'yellow', 1: 'red'}
    ).add_to(m)

    # Add markers for top revenue zip codes
    top_zips = list(zip_revenue.items())[:20]
    for zip_code, data in top_zips:
        coords = get_zip_coords(zip_code)
        if coords:
            folium.CircleMarker(
                location=coords,
                radius=min(data['collected'] / 5000, 30),
                popup=f"{zip_code}<br>Collected: {format_currency(data['collected'])}<br>Clients: {data['clients']}",
                color='darkgreen',
                fill=True,
                fillOpacity=0.7
            ).add_to(m)

    # Calculate totals
    total_collected = sum(d['collected'] for d in zip_revenue.values())

    # Add title
    title_html = '''
    <div style="position: fixed; top: 10px; left: 50px; z-index: 1000;
                background-color: white; padding: 10px; border-radius: 5px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.3);">
        <h3 style="margin: 0;">JCS Law Firm - Revenue by Zip Code</h3>
        <p style="margin: 5px 0 0 0; font-size: 12px;">
            Total collected: {total} | Zip codes: {zips} | Mapped: {mapped}
        </p>
    </div>
    '''.format(total=format_currency(total_collected), zips=len(zip_revenue), mapped=len(heat_data))
    m.get_root().html.add_child(folium.Element(title_html))

    # Save
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    m.save(output_path)
    print(f"Revenue heatmap saved to {output_path}")

    if missing_zips:
        print(f"  Note: {len(missing_zips)} zip codes missing coordinates")

    return output_path


if __name__ == '__main__':
    print("Generating heatmaps...")
    generate_client_heatmap()
    generate_revenue_heatmap()
    print("\nDone! Open the HTML files in a browser to view the interactive maps.")
