<?php

namespace FESULT\Api\Data;

use FESULT\Common\Validate\Types;

class Rooms {

    public function Get($params=NULL) : array
    {
        $Rooms = new \FESULT\Model\Kiss\Rooms();
        $R = [];

        if(isset($params['roomID']) && !empty((int)$params['roomID'])){
            $RoomsR[] = $Rooms->getWithoutTransformer((int)$params['roomID']);
        } else if(isset($params['identifiers']) && !empty($params['identifiers'])){
            $RoomsR = $Rooms->filterByWithoutTransformer([
                'identifiers' => $params['identifiers']
            ])['result'];
        } else {
            $RoomsR = $Rooms->filterByWithoutTransformer([
                'status' => 'active'
            ])['result'];
        }

        if(isset($RoomsR) && !empty($RoomsR)){

            foreach ($RoomsR as $key => $value){
                $R[$key]['id'] = $value['idRooms'];
                $R[$key]['text'] = $value['description'];
                $R[$key]['identifiers'] = $value['identifiers'];
                $R[$key]['label'] = $value['label'];
                $R[$key]['status'] = $value['status'];
                $R[$key]['shortdescription'] = $value['shortdescription'];
                $R[$key]['sizem2'] = $value['sizem2'];
                $R[$key]['handsanitizer_sum'] = $value['handsanitizer_sum'];
            }
        }

        return ['data' => $R];
    }

    public function Post($params = null, $bodyRaw = null): array
    {
        $params = is_array($params) ? $params : [];

        if(is_string($bodyRaw) && trim($bodyRaw) !== ''){
            try {
                $body = json_decode($bodyRaw, true, 512, JSON_THROW_ON_ERROR);

                if(is_array($body)){
                    $params = array_merge($params, $body);
                }
            } catch(\Throwable $throwable){
                return [
                    'error' => 'Ungültiger JSON-Request.',
                    'code' => 400
                ];
            }
        }

        if(!isset($params['description']) || trim((string)$params['description']) === ''){
            return [
                'error' => 'description fehlt.',
                'code' => 400
            ];
        }

        if(!isset($params['identifiers']) || trim((string)$params['identifiers']) === ''){
            return [
                'error' => 'identifiers fehlt.',
                'code' => 400
            ];
        }

        $Rooms = new \FESULT\Model\Kiss\Rooms();
        $roomID = 0;

        if(isset($params['roomID']) && !empty((int)$params['roomID'])){
            $roomID = (int)$params['roomID'];
        } else {
            $RoomsR = $Rooms->filterByWithoutTransformer([
                'identifiers' => $params['identifiers']
            ],1)['result'];

            if(isset($RoomsR[0]['idRooms']) && !empty((int)$RoomsR[0]['idRooms'])){
                $roomID = (int)$RoomsR[0]['idRooms'];
            }
        }

        unset($params['roomID']);

        try {
            if(!empty($roomID)){
                $Rooms->set($params, $roomID);
                $created = false;
            } else {
                $roomID = (int)$Rooms->set($params);
                $created = true;
            }

            return [
                'data' => [
                    'id' => $roomID,
                    'created' => $created
                ]
            ];
        } catch(\Throwable $throwable){
            \FESULT\Core\System\Logger::error([
                'message' => 'Rooms - API-Anfrage konnte nicht verarbeitet werden: '.$throwable->getMessage(),
                'type' => 5,
                'xdata' => [
                    'action' => 'Post',
                    'roomID' => $roomID,
                    'identifiers' => $params['identifiers'],
                    'exception' => get_class($throwable)
                ]
            ]);

            return [
                'error' => 'Raum konnte nicht gespeichert werden.',
                'code' => 500
            ];
        }
    }
}
