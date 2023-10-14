#!/usr/bin/env python
import argparse

import pickle

from pprint import pprint


import json
import sys
import numpy as np
import csv
from urllib.parse import quote
from urllib.request import urlopen, Request
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
BING_DM_API_CUSTOMER_LIMIT = 50 # 50 x 50 = 2500

BING_MAP_API_KEY = ""
try:
    BING_MAP_API_KEY = open('MyBingMapApi.key', mode='r').read().strip()
except OSError:
    sys.stderr.write("ERROR: No file called \"MyBingMapApi.key\" found.\n")
    sys.exit(1)

def geocode_data(address_data, bing_maps_key):
    req_data = dict(address_data)
    req_data['locality'] = quote(address_data['locality'].strip(), safe='')
    req_data['addressLine'] = quote(address_data['addressLine'].strip(), safe='')
    req_data['bing_maps_key'] = bing_maps_key

    geogode_url = ("http://dev.virtualearth.net/REST/v1/Locations" +
                   "?countryRegion=" + str(req_data['countryRegion']) +
                   "&locality=" + str(req_data['locality']) +
                   "&postalCode=" + str(req_data['postalCode']) +
                   "&addressLine=" + str(req_data['addressLine']) +
                   "&maxResults=1" +
                   "&key=" + str(req_data['bing_maps_key']))
    request = Request(geogode_url)
    response = urlopen(request)
    result = json.loads(response.read().decode(encoding='utf-8'))
    lat, lon = result['resourceSets'][0]['resources'][0]['point']['coordinates']

    ret_data = dict(address_data)
    ret_data['latitude'] = lat
    ret_data['longitude'] = lon
    return ret_data


def request_distance_matrix(address_list, travel_mode, bing_maps_key):
    coordinate_list = [str(a['latitude']) + "," + str(a['longitude']) for a in address_list]
    coordinates = ";".join(coordinate_list)

    distance_url = ("https://dev.virtualearth.net/REST/v1/Routes/DistanceMatrix" +
                    "?origins=" + coordinates + "&destinations=" + coordinates +
                    "&travelMode=" + str(travel_mode) +
                    "&distanceUnit=km" +
                    "&key=" + str(bing_maps_key))
    request = Request(distance_url)
    response = urlopen(request)
    result = json.loads(response.read().decode(encoding='utf-8'))

    N = len(address_list)
    D = np.zeros((N, N))
    for cell in result['resourceSets'][0]['resources'][0]['results']:
        D[cell['originIndex'], cell['destinationIndex']] = cell['travelDistance']
    return D


def create_data_model(D):
    # Replace -1 values with a large number
    D[D == -1] = 999999
    return {
        'distance_matrix': D.tolist(),
    }


def save_ordered_addresses_to_csv(manager, routing, solution, locations):
    ordered_addresses = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        ordered_addresses.append(locations[manager.IndexToNode(index)])
        index = solution.Value(routing.NextVar(index))
    ordered_addresses.append(locations[manager.IndexToNode(index)])

    with open('ordered_addresses.csv', 'w', newline='') as csvfile:
        fieldnames = ['addressLine', 'postalCode', 'locality', 'countryRegion']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for address in ordered_addresses:
            writer.writerow(address)

    print("Ordered addresses saved to 'ordered_addresses.csv'.")

def main():
    ## CLI specification ##
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-f', type=argparse.FileType('r'), dest='address_file', help="the tsv (tab separated values) file to load addresses from")
    group.add_argument('-t', type=str, dest='travel_mode', default='Driving', help="travel mode, i.e., 'Driving' (default), 'Walking' or 'Transit' as per Bing Maps API" )
    group.add_argument('-D', type=argparse.FileType('rb'), dest="distance_matrix_file", help="pickled Numpy distance matrix file")
    parser.add_argument('-C', type=float, help="capacity of the vehicles (i.e. C in CVRP)")
    parser.add_argument('-o', type=argparse.FileType('wb'), dest='output_file', help="output file for pickled Numpy distance matrix")
    parser.add_argument('-v', '--verbose', action='store_true', dest='verbosity', help="verbose output")
    args = parser.parse_args()

    locations = []
    if args.address_file:
        for line in args.address_file.readlines():
            line = line.strip()
            if len(line) == 0:
                continue
            parts = line.split('\t')
            if len(parts) < 4 or len(parts) > 6:
                sys.stderr.write("ERROR: Invalid address data line \"" + line + "\"\n")
                sys.stderr.write("Data lines should be in format: addressLine \\t postalCode \\t locality \\t countryRegion [\\t goodsDemand [\\t comment]]\n")
                sys.stderr.write("Exiting.\n")
                sys.exit(1)
            location = {
                "addressLine": parts[0],
                "postalCode": parts[1],
                "locality": parts[2],
                "countryRegion": parts[3],
                "demand": 1 if len(locations) > 0 else 0
            }
            if len(parts) == 5:
                location["demand"] = float(parts[4])
            if len(parts) == 6:
                location["comment"] = parts[5]

            if args.verbosity:
                sys.stderr.write("INFO: Geocoding \"" + location["addressLine"] + "\"\n")
            locations.append(geocode_data(location, BING_MAP_API_KEY))

        if args.verbosity:
            sys.stderr.write("INFO: Filling %d x %d distance matrix.\n" % (len(locations), len(locations)))

        if len(locations) > BING_DM_API_CUSTOMER_LIMIT:
            sys.stderr.write("ERROR: Bing Distance Matrix API is limited to a query with %d\n" % (BING_DM_API_CUSTOMER_LIMIT * BING_DM_API_CUSTOMER_LIMIT))
            sys.stderr.write("distances. Hence, at most %d coordinates can be queried in one go.\n")
            sys.stderr.write("Exiting.\n")
            sys.exit(1)

        D = request_distance_matrix(locations, args.travel_mode, BING_MAP_API_KEY)
        if args.output_file:
            pickle.dump(D, args.output_file)
        print("D = ", end="")
        pprint(D)

        data = create_data_model(D)  # Pass the distance matrix to the function

        # Print the distance matrix for verification
        print("Distance Matrix:")
        for row in data['distance_matrix']:
            print(row)
        print("\n")

    elif args.distance_matrix_file:
        D = pickle.load(args.distance_matrix_file)
        data = create_data_model(D)  # Pass the distance matrix to the function

    else:
        assert False  # argparse should take care that we never arrive here
        pass

    # Create the routing index manager.
    manager = pywrapcp.RoutingIndexManager(len(data['distance_matrix']), 1, 0)

    # Create Routing Model.
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        return data['distance_matrix'][manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)

    # Define cost of each arc.
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Setting first solution heuristic.
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)

    # Solve the problem.
    solution = routing.SolveWithParameters(search_parameters)

    # Print solution on console.
    if solution:
        print_solution(manager, routing, solution, locations)
    else:
        print("No solution found!")
def print_solution(manager, routing, solution, locations):
    """Prints solution on console."""
    print('Objective: {}'.format(solution.ObjectiveValue()))
    index = routing.Start(0)
    route_distance = 0
    print('Optimal Route:')
    while not routing.IsEnd(index):
        print(locations[manager.IndexToNode(index)]['addressLine'])
        previous_index = index
        index = solution.Value(routing.NextVar(index))
        route_distance += routing.GetArcCostForVehicle(previous_index, index, 0)
    print(locations[manager.IndexToNode(index)]['addressLine'])
    print('\nRoute distance: {}'.format(route_distance))



if __name__ == '__main__':
    main()
