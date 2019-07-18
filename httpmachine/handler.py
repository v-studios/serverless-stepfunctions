from json import dumps

# APIG logged this so maybe Lambda can find it?
# {"input": "{}",
#  "name": "57e60897-a8de-11e9-88e4-a774989f6a38",
#  "stateMachineArn":"arn:aws:states:us-east-1:304932368623:stateMachine:HttpmachinechrisStepFunctionsStateMachine-tMMIM057vOFo"}

# Doing APIG Test on GET:
# Sending request to https://states.us-east-1.amazonaws.com/?Action=StartExecutionus-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-1:304932368623:function:httpmachinechris-dev-start/invocations
# Received response. Status: 400, Integration latency: 10 ms
# Endpoint response headers: {x-amzn-RequestId=7db46310-54f0-43bd-967b-dc8abda3a16e, Content-Type=application/x-amz-json-1.0, Content-Length=63}
# Endpoint response body before transformations: {"__type":"com.amazon.coral.service#UnknownOperationException"}
# Execution failed due to configuration error: No match for output mapping and no default output mapping configured. Endpoint Response Status Code: 400
# Method completed with status: 500

# The output of start() appears to get fed to the input of the next state, stop()
# so it is never making it to the APIG output.
# Should we instead *trigger* the next event then return our APIG output

def start(event, context):
    """APIG starts the SM"""
    # print('START Got Task? event=%s', dumps(event))
    # print('TEST_START Got Task? context=%s', dumps(dir(context)))
    #return dumps({'statusCode': 200, 'body': 'STARTED'})
    return {'statusCode': 200, 'body': 'STARTED', 'event': event}
    #return {'statusCode': 200}  # maybe SM doesn't want a lot of return stuff?
    #return {'statusCode': 200, 'body': {'event': dumps(event), 'context': dumps(dir(context))}}

def stop(event, context):
    """APIG starts the SM"""
    return dumps({'statusCode': 200, 'body': 'STOP', 'comment': 'NOT HTTP'})


if __name__ == '__main__':
    print(start({'event': 'here'}, {}))
    print(stop({'event': 'here'}, {}))
