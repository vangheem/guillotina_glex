from guillotina import configure

app_settings = {
    'omdb_api_key': 'plsBanMe',
    'download_folder': '/tmp',
    'bucket_name': 'foobar',
    "auth_extractors": [
        "guillotina.auth.extractors.BasicAuthPolicy",
        "guillotina_glex.auth.TokenAuthPolicy"
    ],
    "auth_token_validators": [
        "guillotina.auth.validators.SaltedHashPasswordValidator",
        "guillotina_glex.auth.TokenValidator"
    ],
}


def includeme(root):
    """
    custom application initialization here
    """
    configure.scan('guillotina_glex.api')
    configure.scan('guillotina_glex.install')
    configure.scan('guillotina_glex.utility')
