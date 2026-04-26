import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


@require_http_methods(["GET", "POST"])
@csrf_exempt
def health(request):
    # Health check endpoint
    # GET: Returns healthy status
    # POST: Accepts JSON and returns success message
    
    if request.method == 'GET':
        return JsonResponse({'status': 'healthy'}, status=200)
    
    # Handle POST
    try:
        data = json.loads(request.body.decode('utf-8'))
        
        if data:
            key = list(data.keys())[0] if isinstance(data, dict) else 'unknown'
            return JsonResponse({
                'status': 200,
                'message': f'Data {key} was successfully received'
            }, status=200)
        
        return JsonResponse({
            'status': 400,
            'message': 'No data provided'
        }, status=400)
    
    except json.JSONDecodeError:
        return JsonResponse({
            'status': 400,
            'message': 'Invalid JSON format'
        }, status=400)
    
    except Exception:
        return JsonResponse({
            'status': 500,
            'message': 'Internal server error'
        }, status=500)

