from json import dumps

def test_start(event, context):
    print('TEST_START Got Task? event=%s', dumps(event))
    print('TEST_START Got Task? context=%s', dumps(dir(context)))
    return {'statusCode': 200, 'body': {'event': dumps(event), 'context': dumps(dir(context))}}

# Testing locally

if __name__ == '__main__':
    print(test_start({}, {}))
