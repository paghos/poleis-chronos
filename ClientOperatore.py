import requests

prenotazione=input("Inserisci il numero della prenotazione: ") 

# Define the URL and parameters
url = 'http://chronos-url/api/convalida'
params = {
    'authenticate-as': 'none-none-none', # Must match the IDs authorized for BackOffice
    'api-token' : 'none-none-none', #Must match the value of the value of API_Token var
    'identity': 'none-none-none', #Set it to something recognisable
    'prenotazione' : prenotazione #Do not touch
}

# Make the GET request
response = requests.post(url, params=params)

# Print the status code and content of the response
print(f"Status Code: {response.status_code}")
print(f"Response Content: {response.text}")
