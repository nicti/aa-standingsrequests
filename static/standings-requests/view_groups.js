standingsApp.controller('GroupsListController', function ($scope, $http) {
    $scope.getData = function () {
        $http.get(urls.groups_json).then(function(response) {
            // Success
            $scope.corps = response.data.corps;
            $scope.alliances = response.data.alliances;
        }, function(response) {
            // Unsuccessful
        });
    };

    $scope.getData();
});