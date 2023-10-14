
import sys
import numpy as np
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from urllib.parse import quote
import json
from urllib.request import urlopen, Request


# Due to the limitation of the free api, one has to batch the distance queries.
BING_DM_API_CUSTOMER_LIMIT = 50

# Use a key loaded from the file "MyBingMapApi.key" containing only *your* key.
BING_MAP_API_KEY = ""
try:
    BING_MAP_API_KEY = open('MyBingMapApi.key', mode='r').read().strip()
except OSError:
    sys.stderr.write("ERROR: No file called \"MyBingMapApi.key\" found.\n")
    sys.exit(1)


def geocode_data(address_data, bing_maps_key):
    # URL encode the address components
    req_data = dict(address_data)
    req_data['locality'] = quote(address_data['locality'].strip(), safe='')
    req_data['addressLine'] = quote(address_data['addressLine'].strip(), safe='')
    req_data['postalCode'] = quote(address_data['postalCode'].strip(), safe='')
    req_data['countryRegion'] = quote(address_data['countryRegion'].strip(), safe='')

    # Construct the geocode URL
    geocode_url = (f"https://dev.virtualearth.net/REST/v1/Locations?"
                   f"countryRegion={req_data['countryRegion']}&"
                   f"locality={req_data['locality']}&"
                   f"postalCode={req_data['postalCode']}&"
                   f"addressLine={req_data['addressLine']}&"
                   f"key={bing_maps_key}")

    # Make the request to Bing Maps API
    request = Request(geocode_url)
    response = urlopen(request)
    response_data = json.load(response)

    # Extract the latitude and longitude from the response
    try:
        coordinates = response_data['resourceSets'][0]['resources'][0]['point']['coordinates']
        return tuple(coordinates)
    except (IndexError, KeyError):
        print(f"Error geocoding address: {address_data['addressLine']}")
        return None

def request_distance_matrix(address_list, travel_mode, bing_maps_key):
    # Convert the list of tuples to a list of strings in the format "latitude,longitude"
    coordinate_list = [f"{a[0]},{a[1]}" for a in address_list]
    coordinates = ";".join(coordinate_list)

    distance_url = ("https://dev.virtualearth.net/REST/v1/Routes/DistanceMatrix" +
                    "?origins=" + coordinates + "&destinations=" + coordinates +
                    "&travelMode=" + travel_mode +
                    "&distanceUnit=km" +
                    "&key=" + bing_maps_key)
    request = Request(distance_url)
    response = urlopen(request)
    result = json.loads(response.read().decode(encoding='utf-8'))

    N = len(address_list)
    D = np.zeros((N, N))
    for cell in result['resourceSets'][0]['resources'][0]['results']:
        D[cell['originIndex'], cell['destinationIndex']] = cell['travelDistance']
    return D

def create_data_model(D):
    return {
        'distance_matrix': D,
    }

def generate_google_maps_url(addresses):
    base_url = "https://www.google.com/maps/dir/"
    formatted_addresses = [address.replace(' ', '+') for address in addresses]
    return base_url + '/'.join(formatted_addresses)

def print_solution(manager, routing, solution, locations, original_addresses):
    """Prints solution on console."""
    print("\nOptimal route:\n")
    index = routing.Start(0)
    plan_output = ''
    route_order = []  # List to store the order of addresses in the solution
    route_distance = 0
    while not routing.IsEnd(index):
        plan_output += f"{original_addresses[manager.IndexToNode(index)]}\n"
        route_order.append(original_addresses[manager.IndexToNode(index)])
        previous_index = index
        index = solution.Value(routing.NextVar(index))
        route_distance += routing.GetArcCostForVehicle(previous_index, index, 0)
    plan_output += f"{original_addresses[manager.IndexToNode(index)]}\n"
    route_order.append(original_addresses[manager.IndexToNode(index)])
    print(plan_output)
    print(f"Route distance: {route_distance}m\n")

    # Generate and print the Google Maps link
    google_maps_link = generate_google_maps_url(route_order)
    print(f"Google Maps Link: {google_maps_link}\n")


def main():
    # Read addresses from the file
    with open('addresses.tsv', 'r') as f:
        locations = []
        original_addresses = []
        for line in f.readlines():
            parts = line.strip().split('\t')
            if len(parts) < 4:
                sys.stderr.write("ERROR: Invalid address data line \"" + line + "\"\n")
                sys.exit(1)
            location = {
                "addressLine": parts[0],
                "postalCode": parts[1],
                "locality": parts[2],
                "countryRegion": parts[3]
            }
            original_addresses.append(parts[0])
            locations.append(geocode_data(location, BING_MAP_API_KEY))

    if len(locations) > BING_DM_API_CUSTOMER_LIMIT:
        sys.stderr.write("ERROR: Bing Distance Matrix API is limited to a query with %d\n" %
                         (BING_DM_API_CUSTOMER_LIMIT * BING_DM_API_CUSTOMER_LIMIT))
        sys.exit(1)

    D = request_distance_matrix(locations, 'Driving', BING_MAP_API_KEY).tolist()
    print("Distance Matrix:")
    for row in D:
        print(row)

    # Solve TSP using OR-Tools
    data = create_data_model(D)
    manager = pywrapcp.RoutingIndexManager(len(data['distance_matrix']), 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        return data['distance_matrix'][manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
    solution = routing.SolveWithParameters(search_parameters)

    if solution:
        print_solution(manager, routing, solution, locations, original_addresses)
    else:
        print("No solution found!")


if __name__ == "__main__":
    main()
