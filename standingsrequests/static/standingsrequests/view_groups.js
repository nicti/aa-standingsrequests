standingsApp.controller('GroupsListController', function ($scope, $http) {
    $scope.getData = function () {
        $http.get(urls.groups_json).then(function(response) {
            // Success
            document.getElementById("tr_spinner_corporations").style.display = 'none';
            document.getElementById("tr_spinner_alliances").style.display = 'none';
            $scope.corps = response.data.corps;
            $scope.alliances = response.data.alliances;
        }, function(response) {
            // Unsuccessful
        });
    };

    $scope.getData();
});