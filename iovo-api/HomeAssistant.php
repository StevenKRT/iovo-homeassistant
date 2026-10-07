<?php

namespace FESULT\Api\Data;

class HomeAssistant {

    public function Get($params = NULL) : array
    {
        return [
            'data' => [
                'name' => 'iovo|doc',
                'integration' => 'home_assistant',
                'version' => 1,
                'resources' => [
                    'rooms' => [
                        'active' => true,
                        'endpoint' => '/Data/Rooms',
                        'read' => true,
                        'update' => true,
                        'create' => false
                    ]
                ]
            ]
        ];
    }
}
