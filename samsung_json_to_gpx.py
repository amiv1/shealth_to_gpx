import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime

ISO_DATE_TIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'


def _get_file_with_type(input, type_):
    for input_file in input:
        if input_file['type'] == type_:
            return input_file

    return None


def _date_from_long_unix_str(str_time):
    return datetime.utcfromtimestamp(str_time / 1000)


def _to_iso(str_time):
    dt = _date_from_long_unix_str(str_time)
    return time.strftime(ISO_DATE_TIME_FORMAT, dt.timetuple())


def _merge_tracks(tracks):
    result = {}
    for track in tracks:
        for row in track:
            if not row.get('start_time'):
                continue

            if row['start_time'] not in result:
                result[row['start_time']] = {}

            result[row['start_time']].update(row)

    return [result[key] for key in sorted(result.keys())]


EXERCISE_RE = re.compile(r'\.com\.samsung\.health\.exercise\.(live_data|location_data)\.json$')
SUPPORTED_TYPES = {'live_data', 'location_data'}
MIN_RECORDS_COUNT = 100

# Global counters
converted_cnt = 0
small_cnt = 0
invalid_cnt = 0

def process_exercise(name, values):
    global converted_cnt, small_cnt, invalid_cnt
    
    if not _get_file_with_type(values, 'location_data'):
        print('Skip track {}: missing location data'.format(name))
        invalid_cnt += 1
        return

    if not os.path.exists('./output/'):
        os.mkdir('./output')

    sources = []
    for source in values:
        with open(source['path']) as src_file:
            sources.append(json.load(src_file))

    data = _merge_tracks(sources)
    if len(data) < MIN_RECORDS_COUNT:
        print('Empty or small track {}'.format(name))
        small_cnt += 1
        return
    
    written = 0

    start_unix = data[0]['start_time']

    output_data = []
    output_data.extend([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx creator="DrA1exGPX" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd http://www.garmin.com/xmlschemas/GpxExtensions/v3 http://www.garmin.com/xmlschemas/GpxExtensionsv3.xsd http://www.garmin.com/xmlschemas/TrackPointExtension/v1 http://www.garmin.com/xmlschemas/TrackPointExtensionv1.xsd" version="1.1" xmlns="http://www.topografix.com/GPX/1/1" xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1" xmlns:gpxx="http://www.garmin.com/xmlschemas/GpxExtensions/v3">',
        '<metadata>',
        '<time>{}</time>'.format(_to_iso(start_unix)),
        '</metadata>',
        '<trk>',
        '<name>Ride at {}</name>'.format(time.strftime('%Y-%m-%d', _date_from_long_unix_str(start_unix).timetuple())),
        '<type>1</type>',
        '<trkseg>'
    ])

    for item in data:
        if not item.get('latitude') or not item.get('longitude'):
            continue

        output_data.extend([
            '<trkpt lat="{}" lon="{}">'.format(item['latitude'], item['longitude']),
            '<time>{}</time>`'.format(_to_iso(item['start_time']))
        ])

        if item.get('altitude'):
            output_data.append('<ele>{}</ele>'.format(item['altitude']))

        if item.get('heart_rate'):
            output_data.extend([
                '<extensions>',
                '<gpxtpx:TrackPointExtension>',
                '<gpxtpx:hr>{}</gpxtpx:hr>'.format(item['heart_rate']),
                '</gpxtpx:TrackPointExtension>',
                '</extensions>'
            ])

        output_data.append('</trkpt>')
        written += 1

    output_data.extend([
        '</trkseg>',
        '</trk>',
        '</gpx>'
    ])

    print('Save track {} with {} points'.format(name, written))
    out_path = './output/{}.gpx'.format(name)
    with open(out_path, 'w+') as out:
        out.write('\n'.join(output_data))
    converted_cnt += 1

if len(sys.argv) < 2:
    print('Path argument missing')
    print('Usage: python3 samsung_json_to_gpx.py /path/to/unpacked/zip/')
    sys.exit(1)

base_path = sys.argv[1]
if not os.path.exists(base_path) or not os.path.isdir(base_path):
    print('Seems like directory "{}" does not exist'.format(base_path))
    sys.exit(2)

jsons_path = os.path.join(base_path, 'jsons/com.samsung.shealth.exercise/')
if not os.path.exists(jsons_path):
    print('Seems like directory is invalid. Missing directory with exercises at "{}"'.format(jsons_path))
    sys.exit(3)

# Collect exercises by UUID
exercises = defaultdict(lambda: [])
file_count = 0
processed_count = 0

print('Scanning for exercise files...')
for root, dirs, files in os.walk(jsons_path):
    for filename in files:
        match = EXERCISE_RE.search(filename)
        if match:
            file_count += 1
            # Extract UUID from filename (everything before .com.samsung...)
            uuid = filename.split('.com.samsung')[0]
            exercise_type = match.group(1)
            exercises[uuid].append({
                'path': os.path.join(root, filename),
                'type': exercise_type
            })
            
            # Process immediately if we have both files
            if len(exercises[uuid]) == 2:
                processed_count += 1
                print(f'Processing exercise {processed_count}: {uuid[:8]}... (found both files)')
                process_exercise(uuid, exercises[uuid])
                del exercises[uuid]  # Free memory

print(f'Found {file_count} exercise files, {processed_count} complete pairs')
print(f'Processing remaining {len(exercises)} exercises...')

# Process remaining exercises with only one file type
for uuid, values in exercises.items():
    processed_count += 1
    print(f'Processing exercise {processed_count}: {uuid[:8]}... ({len(values)} file(s))')
    process_exercise(uuid, values)

print('Done')
print('Converted: {}, Small: {}, Invalid: {}'.format(converted_cnt, small_cnt, invalid_cnt))
